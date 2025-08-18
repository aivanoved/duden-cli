import os
import re
from dataclasses import dataclass
from typing import Self, cast

import bs4 as bs
import httpx
import structlog

from duden_cli.layout.html import (
    clean_page_elements,
    clean_text,
    delete_a_rule,
    dl_split,
    normalize_text,
    strip_a_lexeme,
    strip_italic,
    strip_span,
)

log = structlog.get_logger()

DUDEN_BASE_URL = "https://www.duden.de"
RECHTSCHREIBUNG_URL = f"{DUDEN_BASE_URL}/rechtschreibung/{{word}}"


def terminal_width() -> int:
    size = os.get_terminal_size()

    return size.columns


def _extract_dl(soup: bs.BeautifulSoup) -> list[tuple[str, bs.Tag]]:
    return list(
        map(
            dl_split,
            [cast(bs.BeautifulSoup, _dl) for _dl in soup.find_all(name="dl")],
        )
    )


@dataclass
class InformationCard:
    word: str
    word_type: str | None
    frequency: int | None
    pronunciation: str | None

    @classmethod
    def new(cls, word: str) -> Self:
        return cls(word, None, None, None)

    def wordtype_from_tag(self, tag: bs.Tag | None) -> Self:
        if tag is None:
            return self

        word_type = "".join(clean_text(e) for e in tag.contents)

        return self.__class__(
            self.word,
            word_type,
            self.frequency,
            self.pronunciation,
        )

    def frequency_from_tag(self, tag: bs.Tag | None) -> Self:
        if tag is None:
            return self

        frequency_str = cast(
            str, cast(bs.Tag, clean_page_elements(tag)[0]).attrs["aria-label"]
        )

        frequency_int: int | None = None

        if (
            frequency_str
            == "Gehört zu den 100 häufigsten Wörtern im Dudenkorpus"
        ):
            frequency_int = 5
        elif (
            frequency_str
            == "Gehört zu den 1000 häufigsten Wörtern im Dudenkorpus mit Ausnahme der Top 100"
        ):
            frequency_int = 4
        elif (
            frequency_str
            == "Gehört zu den 10000 häufigsten Wörtern im Dudenkorpus mit Ausnahme der Top 1000"
        ):
            frequency_int = 3
        elif (
            frequency_str
            == "Gehört zu den 100000 häufigsten Wörtern im Dudenkorpus mit Ausnahme der Top 10000"
        ):
            frequency_int = 2
        elif (
            frequency_str
            == "Gehört nicht zu den 100000 häufigsten Wörtern im Dudenkorpus"
        ):
            frequency_int = 1

        return self.__class__(
            self.word,
            self.word_type,
            frequency_int,
            self.pronunciation,
        )

    @classmethod
    def from_soup(cls, soup: bs.BeautifulSoup) -> Self:
        article = soup.find("article")

        word = cast(
            str,
            article.find(name="div", attrs={"class": "lemma"})
            .find(name="h1")
            .find(name="span", attrs={"class": "lemma__main"})
            .text,
        )

        wfp = _extract_dl(cast(bs.BeautifulSoup, article))

        word_type = (
            [e[1] for e in wfp if e[0].startswith("Wortart")] or [None]
        )[0]
        frequency = (
            [e[1] for e in wfp if e[0].startswith("Häufigkeit")] or [None]
        )[0]
        # pronunciation = [e[1] for e in wfp if e[0].startswith("Aussprache")][0]

        return (
            cls.new(normalize_text(word))
            .wordtype_from_tag(word_type)
            .frequency_from_tag(frequency)
        )


@dataclass
class Rechtschreibung:
    hyphenation: str | None
    examples: list[str] | None

    @classmethod
    def from_soup(cls, soup: bs.BeautifulSoup) -> Self:
        article = soup.find("article")

        main_div = article.find("div", attrs={"id": "rechtschreibung"})

        he = _extract_dl(cast(bs.BeautifulSoup, main_div))

        return (
            cls(None, None)
            .hyphenation_from_tag(
                (
                    [h[1] for h in he if h[0].startswith("Worttrennung")]
                    or [None]
                )[0]
            )
            .examples_from_tag(
                ([h[1] for h in he if h[0].startswith("Beispiel")] or [None])[
                    0
                ]
            )
        )

    def hyphenation_from_tag(self, tag: bs.Tag | None) -> Self:
        if tag is None:
            return self

        return self.__class__(cast(str, tag.contents[0]), self.examples)

    def examples_from_tag(self, tag: bs.Tag | None) -> Self:
        if tag is None:
            return self

        preprocessors = [
            strip_span,
            strip_italic,
            delete_a_rule,
            strip_a_lexeme,
        ]

        examples = "".join(
            clean_text(e, preprocessors=preprocessors)  # type: ignore
            for e in tag.contents
        ).split(";")
        examples = [e.strip() for e in examples]

        return self.__class__(self.hyphenation, examples)


@dataclass
class Meaning:
    meaning: str
    examples: list[str] | None
    grammar: str | None
    uses: list[str] | None

    @classmethod
    def from_soup(cls, soup: bs.BeautifulSoup) -> list[Self] | None:
        article = soup.find("article")

        single_div = article.find("div", attrs={"id": "bedeutung"})

        if single_div is not None:
            return cls.from_single(cast(bs.Tag, single_div))

        multi_div = article.find("div", attrs={"id": "bedeutungen"})
        if multi_div is not None:
            return cls.from_many(cast(bs.Tag, multi_div))

        return None

    def examples_from_tag(self, tag: bs.Tag | None) -> Self:
        if tag is None:
            return self

        preprocessors = [
            strip_span,
            strip_italic,
            delete_a_rule,
            strip_a_lexeme,
        ]

        values_unordered_list = cast(bs.Tag, tag.find("ul"))

        examples = [
            "".join(
                normalize_text(clean_text(e, preprocessors=preprocessors))  # type: ignore
                for e in cast(bs.Tag, example).contents
            )
            for example in values_unordered_list.find_all("li")
        ]

        return self.__class__(self.meaning, examples, self.grammar, self.uses)

    @classmethod
    def from_single(cls, tag: bs.Tag) -> list[Self] | None:
        preprocessors = [
            strip_span,
            strip_italic,
            delete_a_rule,
            strip_a_lexeme,
        ]

        meaning_tag = cast(bs.Tag | None, tag.find("p"))
        if meaning_tag is None:
            meaning_tag = cast(bs.Tag | None, tag.find("div"))
        if meaning_tag is None:
            return None

        meaning = normalize_text(
            "".join(
                clean_text(e, preprocessors=preprocessors)  # type: ignore
                for e in meaning_tag.contents
            )
        )

        dls = _extract_dl(cast(bs.BeautifulSoup, tag))

        examples_tag = (
            [e[1] for e in dls if e[0].startswith("Beispiel")] or [None]
        )[0]

        return [cls(meaning, None, None, None).examples_from_tag(examples_tag)]

    @classmethod
    def from_many(cls, tag: bs.Tag) -> list[Self] | None:
        li_items = cast(
            list[bs.Tag],
            tag.find("ol").find_all(
                "li", attrs={"id": re.compile(r"Bedeutung*")}
            ),
        )

        _meanings = [
            (cast(list[Self | None], cls.from_single(e)) or [None])[0]
            for e in li_items
        ]

        return [e for e in _meanings if e is not None] or None


@dataclass
class RechtschreibungLayout:
    information_card: InformationCard
    rechtschreibung: Rechtschreibung
    meanings: list[Meaning] | None
    synonyns: list[str] | None
    etymology: str | None
    grammar: str | None


def rechtschreibung(query: str) -> RechtschreibungLayout | None:
    log.info(f"Querying rechtschreibung for the word '{query}'")

    response = httpx.get(RECHTSCHREIBUNG_URL.format(word=query))

    if response.status_code != 200:
        log.error("unsuccessful")
        raise ValueError(f"'{query}' was not found or has multiple entries")

    soup = bs.BeautifulSoup(response.text, "html.parser")

    information_card = InformationCard.from_soup(soup)
    rechtschreib = Rechtschreibung.from_soup(soup)
    meanings = Meaning.from_soup(soup)

    layout = RechtschreibungLayout(
        information_card=information_card,
        rechtschreibung=rechtschreib,
        meanings=meanings,
        synonyns=None,
        etymology=None,
        grammar=None,
    )

    return layout

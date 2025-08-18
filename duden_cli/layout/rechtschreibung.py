import os
from dataclasses import dataclass
from typing import Self, cast

import bs4 as bs
import httpx
import structlog
from bs4.element import PageElement

from duden_cli.layout.html import (
    clean_page_elements,
    delete_a,
    dl,
    normalize_text,
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
            dl,
            [
                cast(bs.BeautifulSoup, _dl)
                for _dl in soup.find_all(name="dl", attrs={"class": "tuple"})
            ],
        )
    )


@dataclass
class Hinweis:
    word: str
    word_type: str | None
    frequency: int | None
    pronunciation: str | None

    @classmethod
    def new(cls, word: str) -> Self:
        return cls(word, None, None, None)

    def wordtype_from_tag(self, tag: bs.Tag | None) -> Self:
        return self.__class__(
            self.word,
            cast(str, tag.contents[0]) if tag is not None else None,
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

        wfp = _extract_dl(cast(bs.BeautifulSoup, article))[:3]

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

        log.debug(f"{he=}")

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

        log.debug(f"{tag.contents=}")

        simple_contents = tag.contents

        preprocessors = [strip_span, strip_italic, delete_a]

        processed = True

        while processed:
            processed = False

            for processor in preprocessors:
                processed_elements = [processor(e) for e in simple_contents]

                processed = processed or any(e[0] for e in processed_elements)

                simple_contents = sum(
                    (e[1] for e in processed_elements if e[1] is not None),
                    cast(list[PageElement], list()),
                )

        log.debug(f"{simple_contents=}")

        return self


@dataclass
class Bedeutung:
    bedeutung: str
    beispiele: list[str] | None
    grammatik: str | None
    wendungen: list[str] | None


@dataclass
class RechtschreibungLayout:
    hinweis: Hinweis
    rechtschreibung: Rechtschreibung
    bedeutungen: list[Bedeutung] | None
    synonyme: list[str] | None
    herkunft: str | None
    grammatik: str | None


def rechtschreibung(query: str) -> RechtschreibungLayout | None:
    log.info(f"Querying rechtschreibung for the word '{query}'")

    response = httpx.get(RECHTSCHREIBUNG_URL.format(word=query))

    log.debug("got", response=response)

    if response.status_code != 200:
        log.error("unsuccessful")
        raise ValueError(f"'{query}' was not found or has multiple entries")

    soup = bs.BeautifulSoup(response.text, "html.parser")

    hinweis = Hinweis.from_soup(soup)
    rechtschreib = Rechtschreibung.from_soup(soup)

    log.debug(f"{hinweis=}")
    log.debug(f"{rechtschreib=}")

    return None

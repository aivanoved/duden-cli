import os
from dataclasses import dataclass
from typing import Self, cast

import bs4 as bs
import httpx
import structlog

from duden_cli.layout.html import clean_page_elements, dl, normalize_text

log = structlog.get_logger()

DUDEN_BASE_URL = "https://www.duden.de"
RECHTSCHREIBUNG_URL = f"{DUDEN_BASE_URL}/rechtschreibung/{{word}}"


def terminal_width() -> int:
    size = os.get_terminal_size()

    return size.columns


@dataclass
class Hinweis:
    wort: str
    word_type: str | None
    frequency: int | None
    aussprache: str | None

    @classmethod
    def new(cls, wort: str) -> Self:
        return cls(wort, None, None, None)

    def wordtype_from_tag(self, tag: bs.Tag | None) -> Self:
        return self.__class__(
            self.wort,
            cast(str, tag.contents[0]) if tag is not None else None,
            self.frequency,
            self.aussprache,
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
            self.wort,
            self.word_type,
            frequency_int,
            self.aussprache,
        )


@dataclass
class Bedeutung:
    bedeutung: str
    beispiele: list[str] | None
    grammatik: str | None
    wendungen: list[str] | None


@dataclass
class Rechtschreibung:
    worttrennung: str | None
    beispiele: list[str] | None


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
    article = soup.find("article")

    word = cast(
        str,
        article.find(name="div", attrs={"class": "lemma"})
        .find(name="h1")
        .find(name="span", attrs={"class": "lemma__main"})
        .text,
    )

    # spellchecker: off
    wha = [
        dl(_dl)
        for _dl in article.find_all(name="dl", attrs={"class": "tuple"})[:3]  # pyright: ignore[reportUnknownVariableType]
    ]

    word_type = ([e[1] for e in wha if e[0].startswith("Wortart")] or [None])[
        0
    ]
    frequency = (
        [e[1] for e in wha if e[0].startswith("Häufigkeit")] or [None]
    )[0]
    # aussprache = [e[1] for e in wha if e[0].startswith("Aussprache")][0]
    # spellchecker: on

    hinweis = (
        Hinweis.new(normalize_text(word))
        .wordtype_from_tag(word_type)
        .frequency_from_tag(frequency)
    )

    log.debug(f"{hinweis=}")

    return None

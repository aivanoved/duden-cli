import os
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Self, cast, override

import bs4 as bs
import httpx
import structlog
from markdownify import markdownify as md

log = structlog.get_logger()

URL = "https://www.duden.de/rechtschreibung/{word}"


def terminal_width() -> int:
    size = os.get_terminal_size()

    return size.columns


def clean_contents(element) -> list:
    return [e for e in element.contents if e != "\n"]


def clean_tag(element):
    if isinstance(element, bs.Tag):
        return element.contents[0]
    return element


def normal_markdown(element) -> str:
    return cast(
        str,
        md(unicodedata.normalize("NFC", "".join(str(element))).replace("\xa0", " ")),
    )


class Parse:
    @classmethod
    def parse_tag(cls, soup: bs.BeautifulSoup) -> Self | None:
        raise NotImplementedError()

    @classmethod
    def id_name(cls) -> str:
        raise NotImplementedError()


class WordType(Parse, Enum):
    NOUN_MASCULINE = 0
    NOUN_FEMININE = 1
    NOUN_NEUTRAL = 2
    ADJECTIVE = 3
    ADVERB = 4
    WEAK_VERB = 5
    STRONG_VERB = 6
    IRREGULAR_VERB = 7
    ARTICLE = 8
    PROPER_NOUN = 9
    INTERJECTION = 10
    CONJUNCTION = 11
    PARTICLE = 12
    PREFIX = 13
    PREPOSITION = 14
    PRONOUN = 15
    SUFFIX = 16
    NUMERAL = 17

    @classmethod
    @override
    def id_name(cls) -> str:
        return "word_type"

    @classmethod
    @override
    def parse_tag(cls, soup: bs.BeautifulSoup) -> Self | None:
        article = list(soup.find_all("article"))[0]

        word_type_tags = [
            tag
            for tag in article.find_all("dl")
            if "Wortart" in str(tag.find("dt").contents[0])
        ]
        if len(word_type_tags) == 0:
            return None

        contents = cast(
            str, [e for e in word_type_tags[0].find("dd").contents if e != "\n"][-1]
        )

        match contents:
            case "Substantiv, maskulin":
                return cls(cls.NOUN_MASCULINE)
            case "Substantiv, feminin":
                return cls(cls.NOUN_FEMININE)
            case "Substantiv, Neutrum":
                return cls(cls.NOUN_NEUTRAL)
            case "Adjektiv":
                return cls(cls.ADJECTIVE)
            case "Adverb":
                return cls(cls.ADVERB)
            case "schwaches Verb":
                return cls(cls.WEAK_VERB)
            case "starkes Verb":
                return cls(cls.STRONG_VERB)
            case "unregelmäßiges Verb":
                return cls(cls.IRREGULAR_VERB)
            case "Partikel":
                return cls(cls.PARTICLE)
            case "Interjektion":
                return cls(cls.INTERJECTION)
            case _:
                print(contents)
                raise NotImplementedError()

    @override
    def __str__(self: Self) -> str:
        return ""


@dataclass
class Pronunciation(Parse):
    stress: str
    ipa: str

    @classmethod
    @override
    def parse_tag(cls, soup: bs.BeautifulSoup) -> Self | None:
        article = list(soup.find_all("article"))[0]

        pronunciation_tags = [
            tag
            for tag in article.find_all("dl")
            if "Aussprache" in str(tag.find("dt").contents[0])
        ]
        if len(pronunciation_tags) == 0:
            return None

        contents = [e for e in pronunciation_tags[0].find("dd").contents if e != "\n"][
            -1
        ]

        ipas: list[str] = list()
        guides: list[str] = list()

        spans = contents.find_all("span")
        for s in spans:
            class_ = s["class"][0]
            if class_ == "ipa":
                ipas.append(unicodedata.normalize("NFC", clean_contents(s)[0]))
            elif class_ == "pronunciation-guide__text":
                guides.append("".join([normal_markdown(e) for e in clean_contents(s)]))

        return cls(stress=(guides or [""])[0], ipa=(ipas or [""])[0])

    @classmethod
    @override
    def id_name(cls) -> str:
        return "pronunciation"


@dataclass
class SingleMeaning:
    meaning: str
    examples: list[str] | None = None


@dataclass
class Definition(Parse):
    definitions: list[SingleMeaning]

    @classmethod
    def _get_examples(cls, definition) -> list[str] | None:
        examples = [
            clean_contents(e.find("dd"))[0].find_all("li")
            for e in definition.find_all("dl")
            if "Beispiel" in e.find("dt").contents[0]
        ]

        if len(examples) == 0:
            return None

        examples = [
            normal_markdown("".join(map(str, clean_contents(e)))) for e in examples[0]
        ]

        return examples or None

    @classmethod
    def _single_def(cls, single_def) -> Self | None:
        meaning = cast(str, single_def.find("p").contents[0])

        definitions: list[SingleMeaning] = list()
        definitions.append(SingleMeaning(meaning, cls._get_examples(single_def)))

        return cls(definitions)

    @classmethod
    def _multi_def(cls, multi_def) -> Self | None:
        definitions = multi_def.find_all("li", id=re.compile("Bedeutung*"))

        defs = [
            clean_contents(e.find("div", {"class": "enumeration__text"}))
            for e in definitions
        ]

        examples = [cls._get_examples(e) for e in definitions]

        if len(defs) != len(examples):
            raise ValueError()

        defs_str = ["".join(clean_tag(def_element) for def_element in e) for e in defs]

        return cls([SingleMeaning(dfn, exs) for dfn, exs in zip(defs_str, examples)])  # type: ignore

    @classmethod
    @override
    def parse_tag(cls, soup: bs.BeautifulSoup) -> Self | None:
        article = list(soup.find_all("article"))[0]

        single_def = article.find("div", id="bedeutung")
        if single_def:
            return cls._single_def(single_def)

        multi_def = article.find("div", id="bedeutungen")

        if multi_def:
            return cls._multi_def(multi_def)

        return None

    @classmethod
    @override
    def id_name(cls) -> str:
        return "definition"


@dataclass
class Word:
    word: str
    definition: Definition
    word_type: WordType | None
    pronunciation: Pronunciation | None

    @override
    def __str__(self: Self) -> str:
        data = [
            [
                e.meaning,
                "\n".join(
                    f"{i + 1}. {example}" for i, example in enumerate(e.examples or [])
                ),
            ]
            for e in self.definition.definitions
        ]

        from prettytable import PrettyTable

        table = PrettyTable()
        table.field_names = ["Bedeutung", "Beispiel(e)"]

        for row in data:
            table.add_row(row)
            table.add_divider()

        table.align = "l"

        table.max_width = terminal_width() // 2

        return table.get_string()


def definition(word: str) -> Word | None:
    log.info("getting the definition of the word '%s'", word)

    response = httpx.get(URL.format(word=word))

    log.info("got", response=response)

    if response.status_code != 200:
        log.error("unsuccessful")

    soup = bs.BeautifulSoup(response.text, "html.parser")

    pronunciation = Pronunciation.parse_tag(soup)
    word_type = WordType.parse_tag(soup)
    definition = Definition.parse_tag(soup)

    if definition is None:
        return None

    output = Word(
        word=word,
        definition=definition,
        word_type=word_type,
        pronunciation=pronunciation,
    )

    output_str = str(output)

    print(output_str)

    return output

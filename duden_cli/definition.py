import itertools
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Self, cast, override

import bs4 as bs
import httpx
from markdownify import markdownify as md

URL = "https://www.duden.de/rechtschreibung/{word}"


def clean_contents(element) -> list:
    return [e for e in element.contents if e != "\n"]


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

        contents = [e for e in word_type_tags[0].find("dd").contents if e != "\n"][-1]

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
            case _:
                raise NotImplementedError()


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
        guides: list[list[str]] = list()

        spans = contents.find_all("span")
        for s in spans:
            class_ = s["class"][0]
            if class_ == "ipa":
                ipas.append(unicodedata.normalize("NFC", clean_contents(s)[0]))
            elif class_ == "pronunciation-guide__text":
                guides.append(clean_contents(s))

        guide_str: list[str] = list()

        for e in (guides or [[]])[0]:
            guide_str.append(md(unicodedata.normalize("NFC", str(e))))

        return cls(stress="".join(guide_str), ipa=(ipas or [""])[0])

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
    def _single_def(cls, single_def) -> Self | None:
        meaning = cast(str, single_def.find("p").contents[0])
        examples = cast(
            list[str],
            [
                clean_contents(e.find("dd"))[0].find_all("li")
                for e in single_def.find_all("dl")
                if "Beispiel" in e.find("dt").contents[0]
            ],
        )
        examples = cast(
            list[str],
            [
                md(
                    unicodedata.normalize(
                        "NFC", "".join(map(str, clean_contents(e)))
                    ).replace("\xa0", " ")
                )
                for e in itertools.chain(*examples)
            ],
        )

        definitions: list[SingleMeaning] = list()
        definitions.append(SingleMeaning(meaning, examples or None))

        print(f"{definitions=}")

        return cls(definitions)

    @classmethod
    @override
    def parse_tag(cls, soup: bs.BeautifulSoup) -> Self | None:
        article = list(soup.find_all("article"))[0]

        single_def = article.find("div", id="bedeutung")

        if not single_def:
            raise NotImplementedError()

        meaning = cast(str, single_def.find("p").contents[0])
        examples = [
            clean_contents(e.find("dd"))[0].find_all("li")
            for e in single_def.find_all("dl")
            if "Beispiel" in e.find("dt").contents[0]
        ]
        examples = [
            md(
                unicodedata.normalize(
                    "NFC", "".join(map(str, clean_contents(e)))
                ).replace("\xa0", " ")
            )
            for e in itertools.chain(*examples)
        ]

        definitions: list[SingleMeaning] = list()
        definitions.append(SingleMeaning(meaning, examples or None))

        print(f"{definitions=}")

        return cls(definitions)

    @classmethod
    @override
    def id_name(cls) -> str:
        return "definition"


@dataclass
class Word:
    word_type: WordType
    pronunciation: Pronunciation


def definition(word: str) -> Word | None:
    response = httpx.get(URL.format(word=word))

    soup = bs.BeautifulSoup(response.text, "html.parser")

    pronunciation = Pronunciation.parse_tag(soup)
    word_type = WordType.parse_tag(soup)
    definition = Definition.parse_tag(soup)

    print(f"{pronunciation=}")
    print(f"{word_type=}")
    print(f"{definition=}")

    if any(map(lambda e: e is None, [pronunciation, word_type])):
        return None

    return Word(word_type, pronunciation)  # type: ignore

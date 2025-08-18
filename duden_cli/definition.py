import re
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

        return cls([SingleMeaning(dfn, exs) for dfn, exs in zip(defs, examples)])  # type: ignore

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
    word_type: WordType
    definition: Definition
    pronunciation: Pronunciation


def definition(word: str) -> Word | None:
    response = httpx.get(URL.format(word=word))

    soup = bs.BeautifulSoup(response.text, "html.parser")

    pronunciation = Pronunciation.parse_tag(soup)
    word_type = WordType.parse_tag(soup)
    definition = Definition.parse_tag(soup)


    if any(map(lambda e: e is None, [pronunciation, word_type])):
        return None


    return Word(word=word, word_type=word_type, definition=definition, pronunciation=pronunciation)  # type: ignore

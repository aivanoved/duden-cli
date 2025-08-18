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
from prettytable import PrettyTable

log = structlog.get_logger()

DUDEN_BASE_URL = "https://www.duden.de"
DEFINITION_URL = f"{DUDEN_BASE_URL}/rechtschreibung/{{word}}"
SEARCH_URL = f"{DUDEN_BASE_URL}/suchen/dudenonline/{{word}}"


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
    NOUN_MASCULINE_NEUTRAL = 3
    ADJECTIVE = 4
    ADVERB = 5
    WEAK_VERB = 6
    STRONG_VERB = 7
    IRREGULAR_VERB = 8
    ARTICLE = 9
    PROPER_NOUN = 10
    INTERJECTION = 11
    CONJUNCTION = 12
    PARTICLE = 13
    PREFIX = 14
    PREPOSITION = 15
    PRONOUN = 16
    SUFFIX = 17
    NUMERAL = 18

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

        output = None

        match contents:
            case "Substantiv, maskulin":
                output = cls(cls.NOUN_MASCULINE)
            case "Substantiv, feminin":
                output = cls(cls.NOUN_FEMININE)
            case "Substantiv, Neutrum":
                output = cls(cls.NOUN_NEUTRAL)
            case "Substantiv, maskulin, oder Substantiv, Neutrum":
                output = cls(cls.NOUN_MASCULINE_NEUTRAL)
            case "Adjektiv":
                output = cls(cls.ADJECTIVE)
            case "Adverb":
                output = cls(cls.ADVERB)
            case "schwaches Verb":
                output = cls(cls.WEAK_VERB)
            case "starkes Verb":
                output = cls(cls.STRONG_VERB)
            case "unregelmäßiges Verb":
                output = cls(cls.IRREGULAR_VERB)
            case "Partikel":
                output = cls(cls.PARTICLE)
            case "Interjektion":
                output = cls(cls.INTERJECTION)
            case _:
                log.error("unable to decode", word_type=contents)
                raise NotImplementedError()

        log.debug("decoded object", word_type=output)

        return output

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

        output = cls(stress=(guides or [""])[0], ipa=(ipas or [""])[0])

        log.debug("decoded object", pronunciation=output)

        return output

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

        output = cls(definitions)

        log.debug("decoded object", definition=output)

        return output

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

        output = cls([SingleMeaning(dfn, exs) for dfn, exs in zip(defs_str, examples)])  # type: ignore

        log.debug("decoded object", definition=output)

        return output

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

        log.debug("unable to decode", definition=None)
        return None

    @classmethod
    @override
    def id_name(cls) -> str:
        return "definition"


@dataclass
class Grammar(Parse):
    word_type: WordType | None
    grammar: str | list[str] | None

    @classmethod
    @override
    def parse_tag(cls, soup: bs.BeautifulSoup) -> Self | None:
        article = list(soup.find_all("article"))[0]

        word_type = WordType.parse_tag(soup)

        if word_type is None:
            log.debug("unable to decode", word_type=None)
            return None

        grammar = None
        _grammar = article.find("div", id="grammatik")
        if _grammar is None:
            log.debug("unable to decode", grammar=None)
        else:
            _grammar = _grammar.find_all("p")
            if len(_grammar) > 0:
                grammar = _grammar[0].contents

        return cls(
            word_type=word_type,
            grammar=grammar,
        )

    @classmethod
    @override
    def id_name(cls) -> str:
        return "grammar"


@dataclass
class Word:
    word: str
    definition: Definition
    grammar: Grammar | None
    pronunciation: Pronunciation | None

    def meaning_table(self: Self) -> str:
        data = [
            [
                e.meaning,
                "\n".join(
                    f"{i + 1}. {example}" for i, example in enumerate(e.examples or [])
                ),
            ]
            for e in self.definition.definitions
        ]

        table = PrettyTable()
        table.field_names = ["Bedeutung", "Beispiel(e)"]

        for row in data:
            table.add_row(row)
            table.add_divider()

        table.align = "l"
        table.add_autoindex()
        table.max_table_width = terminal_width() - 1

        return table.get_string()

    def grammar_table(self: Self) -> str:
        table = PrettyTable()
        table.field_names = ["Grammatik", ""]

        if self.grammar is None:
            return table.get_string()

        match self.grammar.word_type:
            case WordType.NOUN_MASCULINE:
                table.add_row(["Worttyp", "Substantiv"])
                table.add_divider()
                table.add_row(["Artikel", "der"])
            case WordType.NOUN_FEMININE:
                table.add_row(["Worttyp", "Substantiv"])
                table.add_divider()
                table.add_row(["Artikel", "die"])
            case WordType.NOUN_NEUTRAL:
                table.add_row(["Worttyp", "Substantiv"])
                table.add_divider()
                table.add_row(["Artikel", "das"])
            case WordType.NOUN_MASCULINE_NEUTRAL:
                table.add_row(["Worttyp", "Substantiv"])
                table.add_divider()
                table.add_row(["Artikel", "der oder das"])
            case WordType.WEAK_VERB:
                table.add_row(["Worttyp", "Verb, schwaches"])
            case WordType.STRONG_VERB:
                table.add_row(["Worttyp", "Verb, starkes"])
            case WordType.IRREGULAR_VERB:
                table.add_row(["Worttyp", "Verb, unregelmäßiges"])
            case WordType.ADJECTIVE:
                table.add_row(["Worttyp", "Adjektiv"])
            case WordType.ADVERB:
                table.add_row(["Worttyp", "Adverb"])
            case _:
                pass

        if self.grammar.grammar is not None:
            grammar = self.grammar.grammar
            if isinstance(grammar, str):
                if len(table.rows) > 0:
                    table.add_divider()
                table.add_row(["Other", grammar])
            else:
                for grammar_row in grammar:
                    if len(table.rows) > 0:
                        table.add_divider()
                    table.add_row(["Other", grammar_row])

        table.align = "l"
        table.max_table_width = terminal_width() - 1

        return table.get_string()


def definition(word: str) -> Word | None:
    log.info("getting the definition of the word '%s'", word)

    response = httpx.get(DEFINITION_URL.format(word=word))

    log.info("got", response=response)

    if response.status_code != 200:
        log.error("unsuccessful")
        raise ValueError(f"'{word}' was not found or has multiple entries")

    soup = bs.BeautifulSoup(response.text, "html.parser")

    grammar = Grammar.parse_tag(soup)
    definition = Definition.parse_tag(soup)
    pronunciation = Pronunciation.parse_tag(soup)

    if definition is None:
        return None

    output = Word(
        word=word,
        definition=definition,
        grammar=grammar,
        pronunciation=pronunciation,
    )

    return output

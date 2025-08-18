import os
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Self, cast, override

import bs4 as bs
import structlog
from markdownify import markdownify as md
from rich.console import Console
from rich.table import Table

from duden_cli.layout.rechtschreibung import (
    rechtschreibung,
)

log = structlog.get_logger()

console = Console()

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
        md(
            unicodedata.normalize("NFC", "".join(str(element))).replace(
                "\xa0", " "
            )
        ),
    )


class WordType(Enum):
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
    def parse(cls, word_type: str | None) -> Self | None:
        match word_type:
            case None:
                return None
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
            case "Artikel":
                output = cls(cls.ARTICLE)
            case _:
                log.error("unable to decode", word_type=word_type)
                raise NotImplementedError()

        log.debug("decoded object", word_type=output)

        return output

    @override
    def __str__(self: Self) -> str:
        return ""


@dataclass
class Pronunciation:
    stress: str
    ipa: str

    @classmethod
    def parse_tag(cls, text: str) -> Self | None:
        return cls("", "")


@dataclass
class SingleMeaning:
    meaning: str
    examples: list[str] | None = None

    def example_table(self) -> Table:
        table = Table(title="Beispiel(e)", show_lines=True)
        table.add_column("Beispiel(e)", justify="left")

        for example in self.examples or list():
            table.add_row(example)

        return table


@dataclass
class Definition:
    definitions: list[SingleMeaning]


@dataclass
class Grammar:
    word_type: WordType | None
    grammar: str | list[str] | None


@dataclass
class Word:
    word: str
    definitions: Definition
    grammar: Grammar | None
    pronunciation: Pronunciation | None

    def get_plural(self, *, grammar: Grammar | None = None) -> str | None:
        if self.grammar is None and grammar is None:
            return None

        if grammar is None:
            grammar = cast(Grammar, self.grammar)

        if grammar.word_type not in [
            WordType.NOUN_MASCULINE,
            WordType.NOUN_FEMININE,
            WordType.NOUN_NEUTRAL,
            WordType.NOUN_MASCULINE_NEUTRAL,
        ]:
            return None

        grammar_ = grammar.grammar
        if isinstance(grammar_, list):
            grammar_ = ([None] + [g for g in grammar_ if "Plural" in g])[-1]
        if isinstance(grammar_, str) and "Plural: die" in grammar_:
            return (
                grammar_.split("Plural: die")[1]
                .strip()
                .lstrip()
                .split()[0]
                .strip()
            )

        return None

    def meaning_table(self: Self) -> Table:
        table = Table(title=f"Bedeutung(en) von {self.word}", show_lines=True)
        table.add_column("Bedeutung", justify="left")
        table.add_column("Beispiel(e)", justify="left")

        for e in self.definitions.definitions:
            examples = "\n".join(
                f"{i + 1}. {example}"
                for i, example in enumerate((e.examples or [])[:10])
            )
            table.add_row(e.meaning, examples)

        return table

    def grammar_table(self: Self) -> Table:
        table = Table(title="Grammatik", show_lines=True)
        table.add_column("Grammatik", justify="left")
        table.add_column(self.word, justify="left")

        if self.grammar is None:
            return table

        match self.grammar.word_type:
            case WordType.NOUN_MASCULINE:
                table.add_row("Worttyp", "Substantiv")
                table.add_row("Artikel", "der")
            case WordType.NOUN_FEMININE:
                table.add_row("Worttyp", "Substantiv")
                table.add_row("Artikel", "die")
            case WordType.NOUN_NEUTRAL:
                table.add_row("Worttyp", "Substantiv")
                table.add_row("Artikel", "das")
            case WordType.NOUN_MASCULINE_NEUTRAL:
                table.add_row("Worttyp", "Substantiv")
                table.add_row("Artikel", "der oder das")
            case WordType.WEAK_VERB:
                table.add_row("Worttyp", "Verb, schwaches")
            case WordType.STRONG_VERB:
                table.add_row("Worttyp", "Verb, starkes")
            case WordType.IRREGULAR_VERB:
                table.add_row("Worttyp", "Verb, unregelmäßiges")
            case WordType.ADJECTIVE:
                table.add_row("Worttyp", "Adjektiv")
            case WordType.ADVERB:
                table.add_row("Worttyp", "Adverb")
            case _:
                pass

        if self.grammar.grammar is not None:
            grammar = self.grammar.grammar
            if isinstance(grammar, str):
                table.add_row("Other", grammar)
            else:
                for grammar_row in grammar:
                    table.add_row("Other", grammar_row)

        return table

    def example_table(self, *, meaning: int = 0) -> Table:
        table = Table(
            f"Beispiel(e) für {self.word} mit Bedeutung {meaning + 1}",
            show_lines=True,
        )
        table.add_column("Beispiel(e)", justify="left")

        for example in (
            self.definitions.definitions[meaning].examples or list()
        ):
            table.add_row(example)

        return table


def definition(word: str) -> Word | None:
    log.info("getting the definition of the word '%s'", word)

    layout = rechtschreibung(word)

    if layout is None:
        log.error("unsuccessful")
        raise ValueError(f"'{word}' was not found or has multiple entries")

    word = layout.hinweis.word
    _definitions = layout.bedeutungen or []

    definitions = Definition(
        [SingleMeaning(e.bedeutung, e.beispiele) for e in _definitions]
    )

    grammar = Grammar(WordType.parse(layout.hinweis.word_type), None)

    output = Word(
        word=word,
        definitions=definitions,
        grammar=grammar,
        pronunciation=None,
    )

    return output

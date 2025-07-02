from dataclasses import dataclass
from enum import Enum
import itertools
import re
from statistics import mean
import unicodedata
import typer
import httpx
import bs4 as bs
from typing import Any, Self, cast, override

cli = typer.Typer()

def clean_contents(element) -> list:
    return [e for e in element.contents if e != '\n']

class Parse:
    @classmethod
    def parse_tag(cls, article) -> Self | None:
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
        return 'word_type'

    @classmethod
    @override
    def parse_tag(cls, article) -> Self | None:
        word_type_tags = [tag for tag in article.find_all('dl') if 'Wortart' in str(tag.find('dt').contents[0])]
        if len(word_type_tags) == 0:
            return None

        contents = [e for e in word_type_tags[0].find('dd').contents if e != '\n'][-1]

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
    def parse_tag(cls, article) -> Self | None:
        pronunciation_tags = [tag for tag in article.find_all('dl') if 'Aussprache' in str(tag.find('dt').contents[0])]
        if len(pronunciation_tags) == 0:
            return None

        contents = [e for e in pronunciation_tags[0].find('dd').contents if e != '\n'][-1]

        ipas: list[str] = list()
        guides: list[list[str]] = list()

        spans = contents.find_all('span')
        for s in spans:
            class_ = s['class'][0]
            if class_ == 'ipa':
                ipas.append(s.contents[0])
            elif class_ == 'pronunciation-guide__text':
                guides.append(s.contents)


        guide_str: list[str] = list()

        for e in (guides or [[]])[0]:
            if isinstance(e, bs.Tag):
                guide_str.append("*" + str(e.contents[0]) + "*")
            else:
                guide_str.append(str(e))

        return cls(stress=''.join(guide_str), ipa=(ipas or [''])[0])

    @classmethod
    @override
    def id_name(cls) -> str:
        return 'pronunciation'


@dataclass
class SingleMeaning:
    meaning: str
    examples: list[str] | None = None

@dataclass
class Definition(Parse):
    definitions: list[SingleMeaning]

    @classmethod
    @override
    def parse_tag(cls, article) -> Self | None:
        single_def = article.find('div', id='bedeutung')

        if not single_def:
            raise NotImplementedError()

        meaning = cast(str, single_def.find('p').contents[0])
        examples = [clean_contents(e.find('dd'))[0].find_all('li') for e in single_def.find_all('dl') if 'Beispiel' in e.find('dt').contents[0]]
        examples = [unicodedata.normalize('NFC', cast(str, clean_contents(e)[0])).replace(u'\xa0', u' ') for e in itertools.chain(*examples)]

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


# components: list[Parse] = [Pronunciation, WordType]


@cli.command()
def meaning(word: str) -> str:
    response = httpx.get(f"https://www.duden.de/rechtschreibung/{word}")

    soup = bs.BeautifulSoup(response.text, 'html.parser')

    article = list(soup.find_all('article'))[0]

    pronunciation = Pronunciation.parse_tag(article)
    word_type = WordType.parse_tag(article)
    definition = Definition.parse_tag(article)

    print(f"{pronunciation=}")
    print(f"{word_type=}")

    return response.text



if __name__ == "__main__":
    cli()

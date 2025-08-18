from dataclasses import dataclass
from enum import Enum
import typer
import httpx
import bs4 as bs
from typing import Any, Self, override

cli = typer.Typer()

class Parse:
    @classmethod
    def parse_tag(cls, tag) -> Self | None:
        raise NotImplementedError()

    @classmethod
    def id_name(cls) -> str:
        raise NotImplementedError()

class WordType(Parse, Enum):
    NOUN_MASCULINE = 0
    NOUN_FEMININE = 1
    NOUN_NEUTRAL = 2

    @classmethod
    @override
    def id_name(cls) -> str:
        return 'word_type'

    @classmethod
    @override
    def parse_tag(cls, tag) -> Self | None:
        if 'Wortart' not in str(tag.find('dt').contents[0]):
            return None

        print("parsing word type")

        contents = [e for e in tag.find('dd').contents if e != '\n'][-1]
        print(f"{contents=}")


@dataclass
class Pronunciation(Parse):
    stress: str
    ipa: str

    @classmethod
    @override
    def parse_tag(cls, tag) -> Self | None:
        if 'Aussprache' not in str(tag.find('dt').contents[0]):
            return None

        contents = [e for e in tag.find('dd').contents if e != '\n'][-1]

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
class Word:
    word_type: WordType
    pronunciation: Pronunciation


components: list[Parse] = [Pronunciation, WordType]


@cli.command()
def meaning(word: str) -> str:
    response = httpx.get(f"https://www.duden.de/rechtschreibung/{word}")

    soup = bs.BeautifulSoup(response.text, 'html.parser')

    article = list(soup.find_all('article'))[0]

    dl = list(article.find_all('dl'))

    parsed: list[str] = list()

    for l in dl:
        success = False
        for component in components:
            if component.id_name() in parsed:
                break
            parsed_obj = component.parse_tag(l)
            if parsed_obj is not None and parsed_obj.id_name() not in parsed:
                print(f"{parsed_obj=}")
                parsed.append(parsed_obj.id_name())
                success = True
                break

        # if not success:
        #     print(f"{l=}")
        #     print()

    return response.text



if __name__ == "__main__":
    cli()

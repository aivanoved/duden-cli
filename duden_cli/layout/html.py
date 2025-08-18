import unicodedata
from typing import cast

import bs4 as bs
from bs4.element import PageElement


def clean_tag(element: bs.BeautifulSoup):
    _element = element.div.title
    if isinstance(element, bs.Tag):
        return element.contents[0]
    return element


def normalize_text(text: str) -> str:
    return (
        unicodedata.normalize("NFC", text)
        .replace("\xa0", " ")
        .replace("\xad", "")
    )


def clean_page_elements(tag: bs.Tag) -> list[PageElement]:
    contents = tag.contents
    if len(contents) > 0 and contents[0] == "\n":
        contents = contents[1:]
    if len(contents) > 0 and contents[-1] == "\n":
        contents = contents[:-1]
    return contents


def dl(element: bs.BeautifulSoup) -> tuple[str, bs.Tag]:
    dl_type = cast(str, element.find(name="dt").contents[0])
    dl_value = cast(bs.Tag, element.find(name="dd"))

    return dl_type, dl_value

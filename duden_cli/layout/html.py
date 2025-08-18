import unicodedata
from typing import cast

import bs4 as bs
import structlog
from bs4.element import PageElement

log = structlog.get_logger()


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


def strip_span(element: PageElement) -> tuple[bool, list[PageElement] | None]:
    if isinstance(element, bs.Tag) and element.name == "span":
        return True, element.contents
    return False, [element]


def strip_italic(
    element: PageElement,
) -> tuple[bool, list[PageElement] | None]:
    if isinstance(element, bs.Tag) and element.name == "i":
        return True, element.contents
    return False, [element]


def delete_a(element: PageElement) -> tuple[bool, list[PageElement] | None]:
    if isinstance(element, bs.Tag) and element.name == "a":
        return True, None
    return False, [element]


def dl(element: bs.BeautifulSoup) -> tuple[str, bs.Tag]:
    dl_type = cast(str, element.find(name="dt").contents[0])
    dl_value = cast(bs.Tag, element.find(name="dd"))

    return dl_type, dl_value

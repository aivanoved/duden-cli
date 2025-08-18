import re
import unicodedata
from collections.abc import Callable
from typing import cast

import bs4 as bs
import structlog
from bs4.element import NavigableString, PageElement

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
        .replace("\u202f", " ")
        .replace("\xad", "")
    )


PageElementPreprocessorOutput = tuple[bool, list[PageElement] | None]
PageElementPreprocessor = Callable[
    [PageElement], PageElementPreprocessorOutput
]


def clean_page_elements(tag: bs.Tag) -> list[PageElement]:
    contents = tag.contents
    if len(contents) > 0 and contents[0] == "\n":
        contents = contents[1:]
    if len(contents) > 0 and contents[-1] == "\n":
        contents = contents[:-1]
    return contents


def strip_span(element: PageElement) -> PageElementPreprocessorOutput:
    if isinstance(element, bs.Tag) and element.name == "span":
        return True, element.contents
    return False, [element]


def strip_italic(
    element: PageElement,
) -> PageElementPreprocessorOutput:
    if isinstance(element, bs.Tag) and element.name == "i":
        return True, element.contents
    return False, [element]


def _html_delete_a(
    element: PageElement, *, matching_content: re.Pattern | None = None
) -> PageElementPreprocessorOutput:
    if (
        isinstance(element, bs.Tag)
        and element.name == "a"
        and matching_content is None
    ):
        return True, None
    elif isinstance(element, bs.Tag) and element.name == "a":
        text = normalize_text("".join(str(e) for e in element.contents))
        match = matching_content.match(text)
        return (True, None) if match is not None else (False, [element])
    return False, [element]


def delete_a_pattern(matching_content: re.Pattern) -> PageElementPreprocessor:
    def _delete_a(element: PageElement) -> PageElementPreprocessorOutput:
        return _html_delete_a(element, matching_content=matching_content)

    return _delete_a


def delete_any_a(element: PageElement) -> PageElementPreprocessorOutput:
    return _html_delete_a(element)


def delete_a_rule(element: PageElement) -> PageElementPreprocessorOutput:
    if isinstance(element, bs.Tag):
        attrs = element.get_attribute_list("data-duden-ref-type")
        return (True, None) if "rule" in attrs else (False, [element])

    return False, [element]


def delete_a_icon(element: PageElement) -> PageElementPreprocessorOutput:
    if isinstance(element, bs.Tag):
        attrs = element.get_attribute_list("class")
        return (True, None) if "tuple__icon" in attrs else (False, [element])

    return False, [element]


def strip_a_lexeme(element: PageElement) -> PageElementPreprocessorOutput:
    default_output = False, [element]
    if not isinstance(element, bs.Tag):
        return default_output

    attrs = element.get_attribute_list("data-duden-ref-type")
    if "lexeme" not in attrs:
        return default_output

    lexeme_strs = normalize_text(
        "".join(str(e) for e in element.contents)
    ).split()

    pattern = re.compile(r"\([0-9]+[a-z]*\)")

    return (
        (True, [NavigableString("".join(lexeme_strs[:-1]))])
        if pattern.match(lexeme_strs[-1]) is not None
        else (True, element.contents)
    )


def clean_text(
    element: PageElement,
    preprocessors: list[PageElementPreprocessor] | None = None,
) -> str:
    if preprocessors is None:
        return str(element)

    processed = True

    simple_element = [element]
    while processed:
        processed = False
        for processor in preprocessors:
            processed_elements = [processor(e) for e in simple_element]

            processed = processed or any(e[0] for e in processed_elements)

            simple_element = sum(
                (e[1] for e in processed_elements if e[1] is not None),
                cast(list[PageElement], list()),
            )

    return "".join(str(e) for e in simple_element)


def dl_split(element: bs.BeautifulSoup) -> tuple[str, bs.Tag]:
    dl_type = "".join(
        clean_text(
            e,
            preprocessors=[
                strip_span,
                strip_italic,
                strip_a_lexeme,
                delete_a_rule,
                delete_a_icon,
            ],
        )
        for e in cast(bs.Tag, element.find(name="dt"))
    )
    dl_value = cast(bs.Tag, element.find(name="dd"))

    return dl_type, dl_value

import logging
from copy import deepcopy
from typing import Final, TypeVar, cast, override

import structlog
import typer
from rich.console import Console

from duden_cli.config import CONFIG
from duden_cli.definition import SingleMeaning, WordType, definition

log_level = logging.DEBUG

match CONFIG.cli_verbosity:
    case 0:
        log_level = logging.ERROR
    case 1:
        log_level = logging.WARNING
    case 2:
        log_level = logging.INFO
    case 3:
        log_level = logging.DEBUG
    case _:
        log_level = logging.ERROR


structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(log_level)
)

log = structlog.get_logger()

cli = typer.Typer(pretty_exceptions_enable=False)
console = Console()

T = TypeVar("T")


def safe_list(items: T | list[T]) -> list[T]:
    if not isinstance(items, list):
        return [items]
    return items


class SelectorOptions[T]:
    def __init__(self, options: T | list[T], *, hint: str | None = None):
        self.options: Final = safe_list(deepcopy(options))
        self._str_options: Final = [str(e) for e in self.options]

        if hint is None:
            _hint: str = ", ".join(self._str_options)
        else:
            _hint = hint

        self.hint: Final = _hint

    def check_input(self, to_check: str) -> bool:
        return any(to_check == e for e in self._str_options)

    def cast(self, to_cast: str) -> T | None:
        raise NotImplementedError


class SelectorOptionsInt(SelectorOptions[int]):
    @override
    def cast(self, to_cast: str) -> int | None:
        if not self.check_input(to_cast):
            return None
        return int(to_cast)


class SelectorOptionsStr(SelectorOptions[str]):
    @override
    def cast(self, to_cast: str) -> str | None:
        if not self.check_input(to_cast):
            return None
        return to_cast


def selector[T](description: str, *variants: SelectorOptions[T]) -> T:
    answer = None

    def condition(_answer: str | None) -> T | None:
        if _answer is None:
            return None
        options: list[T | None] = [None]
        options += [
            variant.cast(_answer)
            for variant in variants
            if variant.check_input(_answer)
        ]
        return options[-1]

    answer = None
    while answer is None:
        answer = condition(
            input(
                description
                + " "
                + ", ".join(variant.hint for variant in variants)
                + ": "
            ).strip()
        )

    return answer


@cli.command()
def meaning(word: str) -> None:
    output = definition(word)
    if output:
        console.print(output.grammar_table())
        console.print(output.meaning_table())


def hint_from_definition(definition: SingleMeaning) -> str:
    defined = definition.meaning.split()
    enumerated = " ".join(
        list(
            [f"{word} /{idx + 1}/" for idx, word in enumerate(defined)],
        )
    )

    variants = SelectorOptionsStr(["s", "n"], hint="s for skip, n for new")
    variants_int = SelectorOptionsInt(
        list(range(1, len(defined) + 1)), hint=f"1..{len(defined)}"
    )

    input_ = None

    console.print(f"Select hint: {enumerated}")

    input_ = cast(
        str | int,
        selector(  # type: ignore
            "Enter the number of the hint word",
            variants,
            variants_int,
        ),
    )

    hint = ""

    if isinstance(input_, int):
        hint = "".join(e for e in defined[input_ - 1].strip() if e.isalpha())
    else:
        match input_:
            case "s":
                hint = ""
            case "n":
                hint = input("Enter a hint: ").strip()

    hint = hint.strip(",").strip(";")

    return f"/{hint}/" if hint != "" else hint


@cli.command()
def gen_deck() -> None:
    import genanki

    import duden_cli.anki as anki

    word = input("Ask for word (q for quit): ")
    while word != "q":
        try:
            output = definition(word)
        except:  # noqa: E722
            log.error("Encountered an error: '%s'", word)
            output = None

        if output is None:
            log.info("No card generated for the word: '%s'", word)
            word = input("Ask for word (q for quit): ")
            continue

        for def_idx, def_ in enumerate(output.definitions.definitions):
            console.print(
                f"Definition {def_idx + 1}/{len(output.definitions.definitions)}"
            )
            console.print(def_.meaning)

            add_def = selector(
                "Add this definition",
                SelectorOptionsStr(["y", "s"], hint="y for yes, s for skip"),
            )

            if add_def == "s":
                continue

            hint = None
            if len(output.definitions.definitions) > 1:
                hint = hint or hint_from_definition(def_)
            grammar = None

            if output.grammar is None:
                grammar = None
            elif output.grammar.word_type is WordType.NOUN_MASCULINE:
                grammar_list = ["Artikel - der"]
                plural = output.get_plural()
                if plural:
                    grammar_list.append(f"die {plural}")

                grammar = ", ".join(grammar_list)
            elif output.grammar.word_type is WordType.NOUN_FEMININE:
                grammar_list = ["Artikel - die"]
                plural = output.get_plural()
                if plural:
                    grammar_list.append(f"die {plural}")

                grammar = ", ".join(grammar_list)
            elif output.grammar.word_type is WordType.NOUN_NEUTRAL:
                grammar_list = ["Artikel - das"]
                plural = output.get_plural()
                if plural:
                    grammar_list.append(f"die {plural}")

                grammar = ", ".join(grammar_list)
            elif output.grammar.word_type is WordType.NOUN_MASCULINE_NEUTRAL:
                grammar_list = ["Artikel - der oder das"]
                plural = output.get_plural()
                if plural:
                    grammar_list.append(f"die {plural}")
            elif output.grammar.word_type in [
                WordType.WEAK_VERB,
                WordType.STRONG_VERB,
                WordType.IRREGULAR_VERB,
            ]:
                _grammar = output.grammar.grammar
                if isinstance(_grammar, str):
                    grammar = _grammar
                elif isinstance(_grammar, list):
                    grammar = ", ".join(_grammar)

            example = None
            answer: str | int = input("Add example y/n: ").strip().lower()
            while answer != "y" and answer != "n":
                answer = input("Add example y/n: ").strip().lower()

            if answer == "y":
                example_table = def_.example_table()
                num_rows = example_table.row_count
                console.print(example_table)
                answer = cast(
                    str | int,
                    selector(  # type: ignore
                        "Enter the number of the example",
                        SelectorOptionsStr(
                            ["s", "n"], hint="s for skip, n for new"
                        ),
                        SelectorOptionsInt(
                            list(range(1, num_rows)), hint=f"1..{num_rows}"
                        ),
                    ),
                )

                if answer == "n":
                    example = input("Enter an example: ")
                elif isinstance(answer, int) and def_.examples is not None:
                    example = def_.examples[answer - 1]

            note = genanki.Note(
                model=anki.model,
                fields=[
                    output.word,
                    def_.meaning,
                    hint or "",
                    grammar or "",
                    example or "",
                ],
            )

            anki.deck.add_note(note)

        word = input("Ask for word (q for quit): ")

    genanki.Package(anki.deck).write_to_file(
        f"Deutsch {anki.datetime_suffix()}.apkg"
    )


if __name__ == "__main__":
    cli()

from collections.abc import Callable
from typing import cast

import structlog
import typer
from rich.console import Console

from duden_cli.definition import SingleMeaning, WordType, definition

log = structlog.get_logger()

cli = typer.Typer(pretty_exceptions_enable=False)

console = Console()


def selector(
    description: str, variants: list[str | Callable[[str], bool]]
) -> str:
    answer = None
    variants_str = [e for e in variants if isinstance(e, str)]
    variants_callable = [e for e in variants if not isinstance(e, str)]

    def condition(_answer: str | None) -> bool:
        if _answer is None:
            return False

        result = len(variants_str) > 0 and not any(
            _answer == e for e in variants_str
        )
        result = result or (
            len(variants_callable) > 0
            and not any(check(_answer) for check in variants_callable)
        )

        return result

    while condition(answer):
        answer = input(f"{description}: ").strip().lower()

    return cast(str, answer)


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
            [f"{word} /{idx}/" for idx, word in enumerate(defined)],
        )
    )

    input_ = None

    while input_ is None:
        console.print(f"Definition: {enumerated}")

        input_ = selector(
            "Enter the number of the hint word, s for skip, n for new",
            ["s", "n"],
        )
        input_ = input_.strip().lower()
        if not (input_.isalpha() or input_.isdecimal()):
            input_ = None
        elif input_.isdecimal() and (
            int(input_) >= len(defined) or int(input_) < 0
        ):
            console.print(
                f"Specified number outside of length: {len(defined)}"
            )
            input_ = None
        elif input_.isalpha() and input_ not in ["s", "n"]:
            console.print("Must be one of s or n")
            input_ = None

    hint = ""

    if input_.isdecimal():
        idx = int(input_)
        hint = "".join(e for e in defined[idx].strip() if e.isalpha())
    elif input_.isalpha():
        match input_:
            case "s":
                hint = ""
            case "n":
                hint = input("Enter a hint: ").strip()

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

        for def_ in output.definition.definitions:
            hint = None
            if len(output.definition.definitions) > 1:
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
            answer = input("Add example y/n: ").strip().lower()
            while answer != "y" and answer != "n":
                answer = input("Add example y/n: ").strip().lower()

            if answer == "y":
                console.print(def_.example_table())
                answer = (
                    input(
                        "Enter the number of the example, s for skip, n for new: "
                    )
                    .strip()
                    .lower()
                )

                if answer == "n":
                    example = input("Enter an example: ")
                elif (
                    answer.isnumeric()
                    and def_.examples is not None
                    and len(def_.examples) > 0
                ):
                    idx = int(answer)
                    while idx <= 0 or idx - 1 >= len(def_.examples):
                        idx = int(
                            input(
                                f"Enter a number between 1 and {len(def_.examples)}: "  # type: ignore
                            )
                        )
                    example = def_.examples[idx - 1]

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
        f"Deutsch {anki.DATETIME_SUFFIX}.apkg"
    )


if __name__ == "__main__":
    cli()

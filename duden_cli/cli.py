import structlog
import typer

from duden_cli.definition import SingleMeaning, WordType, definition

log = structlog.get_logger()

kwargs = {
    "pretty_exceptions_enable": False,
}

cli = typer.Typer(**kwargs)


@cli.command()
def meaning(word: str) -> None:
    output = definition(word)
    if output:
        print(output.grammar_table())
        print(output.meaning_table())


def hint_from_definition(definition: SingleMeaning) -> str:
    defined = definition.meaning.split()
    enumerated = " ".join(
        list(
            [f"{word} /{idx}/" for idx, word in enumerate(defined)],
        )
    )

    input_ = None

    while input_ is None:
        print(f"Definition: {enumerated}")

        input_ = input(
            "Enter the number of the hint word, s for skip, n for new: "
        )
        input_ = input_.strip().lower()
        if not (input_.isalpha() or input_.isdecimal()):
            input_ = None
        elif input_.isdecimal() and (
            int(input_) >= len(defined) or int(input_) < 0
        ):
            print(f"Specified number outside of length: {len(defined)}")
            input_ = None
        elif input_.isalpha() and input_ not in ["s", "n"]:
            print("Must be one of s or n")
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

            def get_plural(grammar: str | list[str] | None) -> str | None:
                if isinstance(grammar, list):
                    grammar = ([None] + [g for g in grammar if "Plural" in g])[
                        -1
                    ]
                if isinstance(grammar, str):
                    if "Plural: die" in grammar:
                        return (
                            grammar.split("Plural: die")[1]
                            .strip()
                            .lstrip()
                            .split()[0]
                            .strip()
                        )

                return None

            grammar = None
            if output.grammar is None:
                grammar = None
            elif output.grammar.word_type is WordType.NOUN_MASCULINE:
                grammar_list = ["Artikel - der"]
                plural = get_plural(output.grammar.grammar)
                if plural:
                    grammar_list.append(f"die {plural}")

                grammar = ", ".join(grammar_list)
            elif output.grammar.word_type is WordType.NOUN_FEMININE:
                grammar_list = ["Artikel - die"]
                plural = get_plural(output.grammar.grammar)
                if plural:
                    grammar_list.append(f"die {plural}")

                grammar = ", ".join(grammar_list)
            elif output.grammar.word_type is WordType.NOUN_NEUTRAL:
                grammar_list = ["Artikel - das"]
                plural = get_plural(output.grammar.grammar)
                if plural:
                    grammar_list.append(f"die {plural}")

                grammar = ", ".join(grammar_list)
            elif output.grammar.word_type is WordType.NOUN_MASCULINE_NEUTRAL:
                grammar_list = ["Artikel - der oder das"]
                plural = get_plural(output.grammar.grammar)
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

            note = genanki.Note(
                model=anki.model,
                fields=[output.word, def_.meaning, hint or "", grammar or ""],
            )

            anki.deck.add_note(note)

        word = input("Ask for word (q for quit): ")

    genanki.Package(anki.deck).write_to_file(
        f"Deutsch {anki.DATETIME_SUFFIX}.apkg"
    )


if __name__ == "__main__":
    cli()

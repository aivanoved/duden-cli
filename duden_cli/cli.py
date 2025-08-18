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
    idx = int(
        input(f"Enter the number of the hint word or -1 for no hint: {enumerated}\n")
    )

    return f"/{defined[idx]}/" if idx != -1 else ""


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
                    grammar = ([None] + [g for g in grammar if "Plural" in g])[-1]
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

    genanki.Package(anki.deck).write_to_file(f"Deutsch {anki.DATETIME_SUFFIX}.apkg")


if __name__ == "__main__":
    cli()

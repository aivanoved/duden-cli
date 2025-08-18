import structlog
import typer

from duden_cli.definition import definition

log = structlog.get_logger()

kwargs = {
    "pretty_exceptions_enable": False,
}

cli = typer.Typer(**kwargs)


@cli.command()
def meaning(word: str) -> None:
    output = definition(word)

    print(output)


@cli.command()
def gen_deck() -> None:
    import genanki

    import duden_cli.anki as anki

    word = input("Ask for word (q for quit):")
    while word != "q":
        output = definition(word)
        if output is None:
            log.info("No card generated for the word: '%s'", word)
            word = input("Ask for word (q for quit): ")
            continue

        for def_ in output.definition.definitions:
            note = genanki.Note(
                model=anki.model,
                fields=[output.word, def_.meaning],
            )

            anki.deck.add_note(note)

        word = input("Ask for word (q for quit): ")

    genanki.Package(anki.deck).write_to_file(f"Deutsch {anki.DATETIME_SUFFIX}.apkg")


if __name__ == "__main__":
    cli()

import typer

from duden_cli.definition import Word, definition

kwargs = {
    "pretty_exceptions_enable": False,
}

cli = typer.Typer(**kwargs)


@cli.command()
def meaning(word: str) -> Word | None:
    return definition(word)


if __name__ == "__main__":
    cli()

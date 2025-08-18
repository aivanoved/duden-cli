import typer

from duden_cli.definition import Word, definition

cli = typer.Typer()


@cli.command()
def meaning(word: str) -> Word | None:
    return definition(word)


if __name__ == "__main__":
    cli()

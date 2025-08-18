import typer

from duden_cli.definition import definition

kwargs = {
    "pretty_exceptions_enable": False,
}

cli = typer.Typer(**kwargs)


@cli.command()
def meaning(word: str) -> None:
    output = definition(word)

    print(output)


if __name__ == "__main__":
    cli()

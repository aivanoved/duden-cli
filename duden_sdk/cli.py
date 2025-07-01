import typer
import httpx
import httptools

cli = typer.Typer()


@cli.command()
def meaning(word: str) -> str:
    response = httpx.get(f"https://www.duden.de/rechtschreibung/{word}")

    print(response)
    print(response.text)

    return response.text



if __name__ == "__main__":
    cli()

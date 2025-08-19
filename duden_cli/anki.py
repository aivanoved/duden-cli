import datetime
import random

import genanki


def generate_valid_id() -> int:
    return random.randrange(1 << 30, 1 << 31)


MODEL_ID = 1923456780
DECK_ID = generate_valid_id()

model = genanki.Model(
    model_id=MODEL_ID,
    name="Simple German Model",
    fields=[
        {"name": "Word"},
        {"name": "Definition"},
        {"name": "Hint"},
        {"name": "Grammar"},
        {"name": "Example"},
    ],
    templates=[
        {
            "name": "Simple German Definition",
            "qfmt": "{{Word}} {{Hint}}",
            "afmt": '{{Word}}<hr id="answer">{{Grammar}}<hr>{{Definition}}<hr>{{Example}}',
        },
        {
            "name": "Simple German Explain",
            "qfmt": "{{Definition}}",
            "afmt": '{{Definition}}<hr id="answer">{{Word}}',
        },
    ],
)


def datetime_suffix() -> str:
    return datetime.datetime.now().strftime("%d %B %Y %H:%M:%S")


deck = genanki.Deck(deck_id=DECK_ID, name=f"German {datetime_suffix}")

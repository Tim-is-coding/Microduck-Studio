"""The runtime's sentences (texts.py): plain words, and the same words as the Studio's cards."""

from __future__ import annotations

import json
from pathlib import Path

from duckstudio import texts
from duckstudio.common import Text

I18N = Path(__file__).resolve().parents[3] / "studio" / "src" / "i18n"


def test_card_words_match_the_studio() -> None:
    """A control or option renamed in the Studio must not keep its old name in the log."""
    for column, lang in enumerate(("de", "en")):
        studio = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        for prefix, table in (("ui.", texts.UI_LABELS), ("opt.", texts.OPTION_LABELS)):
            ours = {prefix + k: v[column] for k, v in table.items()}
            theirs = {k: v for k, v in studio.items() if k.startswith(prefix)}
            assert ours == theirs, lang


def test_a_skill_step_reads_like_its_card() -> None:
    options = texts.step_options(
        {"direction": "toward_person", "tempo": "easy", "distance": 60}, {"distance": "cm"}
    )
    de, en = texts.step_skill(2, Text(de="Gehen", en="Walk"), options)
    assert de == "Schritt 2: Gehen (Richtung zur Person, Tempo gemütlich, Abstand 60 cm)."
    assert en == "Step 2: Walk (Direction toward the person, Speed easy, Distance 60 cm)."
    assert texts.step_skill(3, Text(de="Quaken")) == ("Schritt 3: Quaken.", "Step 3: Quaken.")


def test_unknown_controls_show_their_identifier() -> None:
    assert texts.step_options({"spin": "wild"}, {}) == ("spin wild", "spin wild")


def test_movement_in_words() -> None:
    assert texts.movement(vx=0.08, vyaw=0.0013) == ("8 cm/s vorwärts", "8 cm/s forward")
    assert texts.movement(vx=-0.05, vyaw=-0.5) == (
        "5 cm/s rückwärts, dreht 29°/s nach rechts",
        "5 cm/s backward, turning right at 29°/s",
    )
    assert texts.movement(vy=0.03) == ("3 cm/s seitwärts nach links", "3 cm/s sideways to the left")
    assert texts.movement() == ("steht still", "standing still")


def test_numbers_follow_the_language() -> None:
    assert texts.num(0.8) == ("0,8", "0.8")
    de, en = texts.perceive_found(("Person", "Person"), 1.25, 20.0, left=True)
    assert de == "Person gefunden: 1,2 m, 20° links." and en == "Person found: 1.2 m, 20° left."

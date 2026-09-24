from __future__ import annotations

from duckstudio.executor.tree import normalize_phrase, phrase_in


def test_normalize_drops_punctuation_and_case() -> None:
    assert normalize_phrase("  Okay, „Folge mir“!  ") == "okay folge mir"
    assert normalize_phrase("Über-Ente") == "über ente"


def test_phrase_in_counts_the_words_heard_in_a_row() -> None:
    assert phrase_in("Folge mir", "okay folge mir bitte") == 2
    assert phrase_in("Stopp", "Stopp.") == 1
    assert phrase_in("Stopp", "Stoppuhr") == 0
    assert phrase_in("Folge mir", "folge bitte mir") == 0
    assert phrase_in("", "anything") == 0

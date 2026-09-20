"""Every sentence the Studio shows, in both languages (CLAUDE.md §3.7).

One function per message, returning `(de, en)`, so a translation is never far from the
original and a third language is one file to touch. Identifiers — skill ids, signal names,
backend kinds — stay in the event's `data`, never in the sentence.

The runtime does not know which language the Studio is showing: it sends both and the
Studio picks (`Event.text`). Names of skills and behaviors come from their manifests, which
carry `de` and an optional `en` of their own; `Text.get` falls back to German.
"""

from __future__ import annotations

from .common import Text

Bilingual = tuple[str, str]

# Signals in the language of someone watching a duck, not of the condition string.
SIGNALS: dict[str, Bilingual] = {
    "target_reached": ("Ziel erreicht", "target reached"),
    "target_found": ("Ziel gefunden", "target found"),
    "tof_distance": ("Hindernis zu nah", "obstacle too close"),
    "fallen": ("umgefallen", "fallen over"),
    "motor_hot": ("Motor zu heiß", "motor too hot"),
    "timeout": ("Zeit abgelaufen", "time is up"),
    "standing": ("steht wieder", "standing again"),
    "sitting": ("sitzt", "sitting"),
    "person_found": ("Person gefunden", "person found"),
    "object_grasped": ("Gegenstand gegriffen", "object grasped"),
    "battery": ("Akku", "battery"),
}

RESERVED_ACTIONS: dict[str, Bilingual] = {
    "resume": ("weitermachen", "resume"),
    "abort": ("abbrechen", "abort"),
    "stop": ("anhalten", "stop"),
    "retry": ("noch einmal", "retry"),
    "continue": ("weiter", "continue"),
}

BACKENDS: dict[str, Bilingual] = {
    "mock": ("Attrappe (Mock)", "mock duck"),
    "sim": ("Simulation (MuJoCo)", "simulation (MuJoCo)"),
    "duck": ("Ente", "the duck"),
}


def signal(name: str) -> Bilingual:
    return SIGNALS.get(name, (name, name))


def action(name: str) -> Bilingual:
    return RESERVED_ACTIONS.get(name, (name, name))


def backend(kind: str) -> Bilingual:
    return BACKENDS.get(kind, (kind, kind))


def name_of(text: Text) -> Bilingual:
    """A manifest's own name, German and whatever it offers as English."""
    return text.de, text.get("en")


def quoted(text: Text) -> Bilingual:
    de, en = name_of(text)
    return f"„{de}“", f"“{en}”"


def joined(parts: list[Bilingual], separator: Bilingual = (", ", ", ")) -> Bilingual:
    return separator[0].join(p[0] for p in parts), separator[1].join(p[1] for p in parts)


# -- behaviors ---------------------------------------------------------------------------


def behavior_started(name: Text) -> Bilingual:
    de, en = quoted(name)
    return f"{de} gestartet.", f"{en} started."


def behavior_done(name: Text) -> Bilingual:
    de, en = quoted(name)
    return f"{de} fertig.", f"{en} finished."


def behavior_failed(name: Text, reason: Bilingual) -> Bilingual:
    de, en = quoted(name)
    return f"{de} abgebrochen: {reason[0]}", f"{en} gave up: {reason[1]}"


def behavior_aborted(by_rule: bool = False) -> Bilingual:
    if by_rule:
        return "Ablauf gestoppt (Regel).", "Behavior stopped (rule)."
    return "Ablauf gestoppt.", "Behavior stopped."


def behavior_saved(name: Text) -> Bilingual:
    de, en = quoted(name)
    return f"{de} gespeichert.", f"{en} saved."


def behavior_deleted(name: Text) -> Bilingual:
    de, en = quoted(name)
    return f"{de} gelöscht.", f"{en} deleted."


def stopped_from(source: str) -> Bilingual:
    if source == "notstopp":
        return "Notstopp", "emergency stop"
    return "vom Studio gestoppt", "stopped from the Studio"


def preempted_by(source: str) -> Bilingual:
    who = "Gamepad" if source == "gamepad" else source
    return f"{who} übernimmt: Ablauf gestoppt.", f"{who} takes over: behavior stopped."


def preempted_reason(source: str) -> Bilingual:
    who = "Gamepad" if source == "gamepad" else source
    return f"{who} hat übernommen", f"{who} took over"


# -- steps -------------------------------------------------------------------------------


def step_ask(number: int, question: Text) -> Bilingual:
    de, en = quoted(question)
    return f"Schritt {number}: Frage die KI {de}", f"Step {number}: asking the model {en}"


def step_look_for(number: int, query: str) -> Bilingual:
    what = {"person.nearest": ("die nächste Person", "the nearest person")}.get(
        query, (query, query)
    )
    return f"Schritt {number}: Suche {what[0]}.", f"Step {number}: looking for {what[1]}."


def step_skill(number: int, skill: Text, options: str) -> Bilingual:
    de, en = name_of(skill)
    tail = f" ({options})." if options else "."
    return f"Schritt {number}: {de}{tail}", f"Step {number}: {en}{tail}"


def step_wait(number: int, duration: str) -> Bilingual:
    return f"Schritt {number}: Warte {duration}.", f"Step {number}: waiting {duration}."


def step_ended(number: int, ok: bool, reason: Bilingual) -> Bilingual:
    return (
        f"Schritt {number} {'fertig' if ok else 'gescheitert'}: {reason[0]}",
        f"Step {number} {'done' if ok else 'failed'}: {reason[1]}",
    )


def step_failed_plain() -> Bilingual:
    return "Schritt fehlgeschlagen", "step failed"


def action_failed(what: Bilingual) -> Bilingual:
    return f"{what[0]} fehlgeschlagen", f"{what[1]} failed"


def resumed(number: int) -> Bilingual:
    return f"Weiter mit Schritt {number}.", f"Back to step {number}."


def interrupt_started(on: str, actions: list[Bilingual]) -> Bilingual:
    what = joined(actions)
    sig = signal(on)
    return (
        f"Unterbrechung: {sig[0]} → {what[0]}.",
        f"Interrupt: {sig[1]} → {what[1]}.",
    )


def recovery_failed(on: str) -> Bilingual:
    sig = signal(on)
    return f"{sig[0]} — Erholung klappt nicht.", f"{sig[1]} — recovery is not working."


def aborted_by_rule() -> Bilingual:
    return "abgebrochen durch Regel", "aborted by a rule"


# -- perception --------------------------------------------------------------------------


def perceive_found(
    what: Bilingual, distance_m: float | None, degrees: float, left: bool
) -> Bilingual:
    side = ("links", "left") if left else ("rechts", "right")
    near = (
        (f"{distance_m:.1f} m, ", f"{distance_m:.1f} m, ") if distance_m is not None else ("", "")
    )
    return (
        f"{what[0]} gefunden: {near[0]}{degrees:.0f}° {side[0]}.",
        f"{what[1]} found: {near[1]}{degrees:.0f}° {side[1]}.",
    )


def target_label(question: Text) -> Bilingual:
    de, en = quoted(question)
    return f"Ziel {de}", f"Target {en}"


def person_label() -> Bilingual:
    return "Person", "Person"


def nothing_found(vlm: bool) -> Bilingual:
    if vlm:
        return "Nichts gefunden", "Nothing found"
    return "Niemand zu sehen", "Nobody in sight"


def searching(nothing: Bilingual, skill: Text, seconds: float) -> Bilingual:
    de, en = name_of(skill)
    return (
        f"{nothing[0]}: {de}, {seconds:g} Sekunden.",
        f"{nothing[1]}: {en}, {seconds:g} seconds.",
    )


def vlm_not_allowed() -> Bilingual:
    return (
        "Der Ablauf fragt eine KI, hat sie aber nicht erlaubt.",
        "This behavior asks a model without opting in to one.",
    )


def vlm_sending(provider: str, question: str) -> Bilingual:
    return (
        f"Bild wird an „{provider}“ gesendet: „{question}“",
        f"Sending a picture to “{provider}”: “{question}”",
    )


def vlm_provider_mismatch(allowed: str, configured: str) -> Bilingual:
    return (
        f"„{allowed}“ ist im Ablauf erlaubt, die Runtime sendet an „{configured}“ — "
        f"es wird kein Bild gesendet.",
        f"This behavior allows “{allowed}” but the runtime is set up for “{configured}” — "
        f"no picture is sent.",
    )


def vlm_not_configured(provider: str) -> Bilingual:
    hint = " (ANTHROPIC_API_KEY fehlt)" if provider == "anthropic" else ""
    hint_en = " (ANTHROPIC_API_KEY is not set)" if provider == "anthropic" else ""
    return (
        f"KI-Dienst „{provider}“ ist nicht eingerichtet{hint} — es wird kein Bild gesendet.",
        f"The model “{provider}” is not set up{hint_en} — no picture is sent.",
    )


def vlm_stub_stands_in(allowed: str) -> Bilingual:
    return (
        f"„{allowed}“ ist nicht eingerichtet; die lokale Attrappe antwortet. "
        f"Es verlässt kein Bild die Runtime.",
        f"“{allowed}” is not set up; the local stub answers instead. "
        f"No picture leaves the runtime.",
    )


def vlm_budget_spent(calls: int) -> Bilingual:
    return (
        f"{calls} KI-Anfragen gestellt — Schluss damit, bis der Ablauf neu startet.",
        f"{calls} model questions asked — no more until the behavior starts again.",
    )


def vlm_failed(error: str) -> Bilingual:
    return (
        f"KI-Dienst konnte nicht antworten: {error}",
        f"The model could not answer: {error}",
    )


def vlm_answer(answer: str, found: bool, *, stub: bool = False) -> Bilingual:
    """The model's own sentence when it wrote one, ours when it did not."""
    if answer:
        return answer, answer  # whatever language the model answered in
    if stub:  # our stand-in must never sound like a model that understood the question
        if found:
            return (
                "Attrappe: etwas Auffälliges im Bild — kein echtes Modell, nur ein Fleck.",
                "Stub: something stands out in the picture — not a model, just a blob.",
            )
        return "Attrappe: nichts Auffälliges im Bild.", "Stub: nothing stands out in the picture."
    return (
        ("Etwas gefunden.", "Found something.") if found else ("Nichts gefunden.", "Nothing found.")
    )


# -- safety, intents, backend --------------------------------------------------------------


def speech_heard(text: str) -> Bilingual:
    return f"Gehört: „{text.strip()}“", f"Heard: “{text.strip()}”"


def intent_sent(skill: Text, description: str) -> Bilingual:
    de, en = name_of(skill)
    return f"{de}: {description}.", f"{en}: {description}."


def intent_clamped(skill: Text, description: str) -> Bilingual:
    de, en = name_of(skill)
    return f"{de}: Werte begrenzt ({description}).", f"{en}: values clamped ({description})."


def behavior_sent(skill: Text) -> Bilingual:
    de, en = name_of(skill)
    return f"{de} gestartet.", f"{en} started."


def emergency_stop() -> Bilingual:
    return "Notstopp: Ente angehalten.", "Emergency stop: the duck was stopped."


def watchdog_tripped() -> Bilingual:
    return (
        "Executor meldet sich nicht mehr: Ente angehalten.",
        "The executor went quiet: the duck was stopped.",
    )


def battery_low() -> Bilingual:
    return "Akku zu niedrig", "battery too low"


def precondition_failed(failed: list[str]) -> Bilingual:
    what = ", ".join(failed)
    return f"Voraussetzung nicht erfüllt: {what}", f"Precondition not met: {what}"


def duck_refused(error: str) -> Bilingual:
    return f"Ente lehnt ab ({error})", f"The duck refused ({error})"


def connection_lost(error: str) -> Bilingual:
    return f"Verbindung zur Ente verloren ({error})", f"Lost the connection to the duck ({error})"


def executor_crashed(error: str) -> Bilingual:
    return f"Fehler im Executor: {error}", f"Executor error: {error}"


def backend_connected(kind: str) -> Bilingual:
    de, en = backend(kind)
    return f"{de} verbunden.", f"{en} connected."


def backend_unavailable(kind: str) -> Bilingual:
    de, en = backend(kind)
    hint = (
        (" Starte sie mit sim/up.sh.", " Start it with sim/up.sh.") if kind == "sim" else ("", "")
    )
    return f"{de} nicht erreichbar.{hint[0]}", f"{en} is not reachable.{hint[1]}"


def backend_lost(kind: str, error: str) -> Bilingual:
    de, en = backend(kind)
    return f"{de}: Verbindung verloren ({error}).", f"{en}: connection lost ({error})."

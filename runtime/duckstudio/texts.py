"""Every sentence the Studio shows, in both languages (CLAUDE.md §3.7).

One function per message, returning `(de, en)`, so a translation is never far from the
original and a third language is one file to touch. Identifiers — skill ids, signal names,
backend kinds — stay in the event's `data`, never in the sentence.

The runtime does not know which language the Studio is showing: it sends both and the
Studio picks (`Event.text`). Names of skills and behaviors come from their manifests, which
carry `de` and an optional `en` of their own; `Text.get` falls back to German.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from .common import Text

Bilingual = tuple[str, str]


def num(value: float, digits: int = 1) -> Bilingual:
    """A number as each language writes it: 0,8 in German, 0.8 in English (like the Studio)."""
    en = f"{value:.{digits}f}"
    return en.replace(".", ","), en


# A card's controls and their options, in the words the Studio's cards use: the same entries
# as `ui.*` and `opt.*` in studio/src/i18n/{de,en}.json (a test keeps them equal). A manifest
# from the Hub with a control or option not listed here shows its identifier, like the card.
UI_LABELS: dict[str, Bilingual] = {
    "tempo": ("Tempo", "Speed"),
    "direction": ("Richtung", "Direction"),
    "distance": ("Abstand", "Distance"),
    "pattern": ("Muster", "Pattern"),
    "style": ("Art", "Style"),
}
OPTION_LABELS: dict[str, Bilingual] = {
    "slow": ("langsam", "slow"),
    "easy": ("gemütlich", "easy"),
    "brisk": ("zügig", "brisk"),
    "toward_person": ("zur Person", "toward the person"),
    "straight": ("geradeaus", "straight ahead"),
    "toward_target": ("zum Ziel", "toward the target"),
    "sweep": ("hin und her", "back and forth"),
    "left": ("nach links", "to the left"),
    "right": ("nach rechts", "to the right"),
    "short": ("kurz", "short"),
    "double": ("doppelt", "double"),
}


def option_value(value: object, unit: str | None = None) -> Bilingual:
    """One control's value as the card shows it: a named option, a tick, or a number."""
    if isinstance(value, bool):
        return ("✓", "✓") if value else ("–", "–")
    if isinstance(value, str):
        return OPTION_LABELS.get(value, (value, value))
    if isinstance(value, int | float):
        de, en = num(float(value), 0 if float(value).is_integer() else 1)
        tail = f" {unit}" if unit else ""
        return de + tail, en + tail
    return str(value), str(value)


def step_options(values: Mapping[str, object], units: Mapping[str, str | None]) -> Bilingual:
    """`{direction: toward_person, distance: 60}` → „Richtung zur Person, Abstand 60 cm“."""
    parts = []
    for key, value in values.items():
        label = UI_LABELS.get(key, (key, key))
        shown = option_value(value, units.get(key))
        parts.append((f"{label[0]} {shown[0]}", f"{label[1]} {shown[1]}"))
    return joined(parts)


# Below these, a velocity is the controller's jitter, not something the duck is doing.
STILL_M_S = 0.005
STILL_RAD_S = math.radians(2.0)


def movement(vx: float = 0.0, vy: float = 0.0, vyaw: float = 0.0) -> Bilingual:
    """A `robot.move` command as someone watching the duck would say it."""
    parts: list[Bilingual] = []
    if abs(vx) >= STILL_M_S:
        speed = num(abs(vx) * 100, 0)
        way = ("vorwärts", "forward") if vx > 0 else ("rückwärts", "backward")
        parts.append((f"{speed[0]} cm/s {way[0]}", f"{speed[1]} cm/s {way[1]}"))
    if abs(vy) >= STILL_M_S:
        speed = num(abs(vy) * 100, 0)
        way = ("nach links", "to the left") if vy > 0 else ("nach rechts", "to the right")
        parts.append((f"{speed[0]} cm/s seitwärts {way[0]}", f"{speed[1]} cm/s sideways {way[1]}"))
    if abs(vyaw) >= STILL_RAD_S:
        rate = num(math.degrees(abs(vyaw)), 0)
        way = ("links", "left") if vyaw > 0 else ("rechts", "right")
        parts.append((f"dreht {rate[0]}°/s nach {way[0]}", f"turning {way[1]} at {rate[1]}°/s"))
    if not parts:
        return "steht still", "standing still"
    return joined(parts)


def look_at(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Bilingual:
    """A `robot.look` point (duck frame, metres) as a direction."""
    ahead = num(x)
    parts = [(f"{ahead[0]} m voraus", f"{ahead[1]} m ahead")]
    if abs(y) >= 0.05:
        side = num(abs(y))
        way = ("links", "left") if y > 0 else ("rechts", "right")
        parts.append((f"{side[0]} m {way[0]}", f"{side[1]} m {way[1]}"))
    if abs(z) >= 0.05:
        way = ("nach oben", "up") if z > 0 else ("nach unten", "down")
        parts.append(way)
    what = joined(parts)
    return f"schaut {what[0]}", f"looking {what[1]}"


def intent_params(
    intent: str, params: Mapping[str, float], units: Mapping[str, str | None]
) -> Bilingual:
    """What an intent asks of the duck, in words where we know the intent, else with units."""
    if intent == "robot.move":
        return movement(**{k: params[k] for k in ("vx", "vy", "vyaw") if k in params})
    if intent == "robot.look":
        return look_at(**{k: params[k] for k in ("x", "y", "z") if k in params})
    parts = []
    for key, value in params.items():
        shown = num(value, 2)
        tail = f" {units[key]}" if units.get(key) else ""
        parts.append((f"{key} {shown[0]}{tail}", f"{key} {shown[1]}{tail}"))
    return joined(parts)


# Signals in the language of someone watching a duck, not of the condition string.
SIGNALS: dict[str, Bilingual] = {
    "target_reached": ("Ziel erreicht", "target reached"),
    "target_found": ("Ziel gefunden", "target found"),
    "tof_distance": ("Hindernis zu nah", "obstacle too close"),
    "fallen": ("umgefallen", "fallen over"),
    "motor_hot": ("Motor zu heiß", "motor too hot"),
    "timeout": ("Zeit abgelaufen", "time is up"),
    "standing": ("steht wieder", "standing again"),
    "steady": ("steht wieder sicher", "steady on its feet again"),
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
    "mock": ("Übungsente", "the practice duck"),
    "sim": ("Simulation (MuJoCo)", "simulation (MuJoCo)"),
    "duck": ("Ente", "the duck"),
}


def signal(name: str) -> Bilingual:
    return SIGNALS.get(name, (name, name))


def action(name: str) -> Bilingual:
    return RESERVED_ACTIONS.get(name, (name, name))


def backend(kind: str) -> Bilingual:
    return BACKENDS.get(kind, (kind, kind))


def _backend_subject(kind: str) -> Bilingual:
    """The backend at the start of a sentence: "The duck", "Simulation (MuJoCo)"."""
    de, en = backend(kind)
    return de, en[:1].upper() + en[1:]


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


def skill_imported(name: Text, repo: str) -> Bilingual:
    de, en = quoted(name)
    return (
        f"Baustein {de} von {repo} hinzugefügt.",
        f"Building block {en} added from {repo}.",
    )


def skill_removed(name: Text) -> Bilingual:
    de, en = quoted(name)
    return f"Baustein {de} entfernt.", f"Building block {en} removed."


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


def step_skill(number: int, skill: Text, options: Bilingual = ("", "")) -> Bilingual:
    de, en = name_of(skill)
    return (
        f"Schritt {number}: {de}{f' ({options[0]}).' if options[0] else '.'}",
        f"Step {number}: {en}{f' ({options[1]}).' if options[1] else '.'}",
    )


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


AHEAD_DEG = 3.0  # same threshold as the Studio's "genau voraus" (LivePane.sightingSentence)


def perceive_found(
    what: Bilingual, distance_m: float | None, degrees: float, left: bool
) -> Bilingual:
    side = ("links", "left") if left else ("rechts", "right")
    far = num(distance_m) if distance_m is not None else None
    near = (f"{far[0]} m, ", f"{far[1]} m, ") if far else ("", "")
    if abs(degrees) < AHEAD_DEG:  # "0° links" read like a direction; the Studio says it too
        ahead = (f"{far[0]} m ", f"{far[1]} m ") if far else ("", "")
        return (
            f"{what[0]} gefunden: {ahead[0]}genau voraus.",
            f"{what[1]} found: {ahead[1]}straight ahead.",
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


# Vendor ids as a person says them; the same names as `vlm.provider.*` in the Studio.
VENDOR_NAMES = {"google": "Google", "anthropic": "Anthropic", "openai": "OpenAI"}


def vendor_name(vendor: str) -> str:
    return VENDOR_NAMES.get(vendor, vendor)


def vlm_sending(provider: str, question: str) -> Bilingual:
    who = vendor_name(provider)
    return (
        f"Bild wird an {who} gesendet: „{question}“",
        f"Sending a picture to {who}: “{question}”",
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
    who = vendor_name(allowed)
    return (
        f"Für {who} ist kein Schlüssel hinterlegt (Tab „KI-Anbieter“); die lokale Attrappe "
        f"antwortet. Es verlässt kein Bild die Runtime.",
        f"No key for {who} yet (the “AI vendors” tab); the local stub answers instead. "
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


def intent_sent(skill: Text, description: Bilingual) -> Bilingual:
    de, en = name_of(skill)
    return f"{de}: {description[0]}.", f"{en}: {description[1]}."


def intent_clamped(skill: Text, description: Bilingual) -> Bilingual:
    de, en = name_of(skill)
    return (
        f"{de}: Werte begrenzt ({description[0]}).",
        f"{en}: values clamped ({description[1]}).",
    )


def intent_refused(skill: Text, reason: str, detail: Bilingual = ("", "")) -> Bilingual:
    """Why the gate did not send a command. It was German only until 2026-09-24."""
    de, en = name_of(skill)
    why = {
        "no_health_snapshot": (
            "noch keine Zustandsdaten von der Ente",
            "no state from the duck yet",
        ),
        "battery_low": ("Akku zu niedrig", "battery too low"),
        "precondition_failed": ("Voraussetzung nicht erfüllt", "precondition not met"),
        "unknown_param": ("unbekannter Parameter", "unknown parameter"),
        "rate_limited": ("zu viele Befehle pro Sekunde", "too many commands per second"),
    }
    if reason == "skill_has_no_intent":
        return f"{de} ist kein Bewegungs-Intent.", f"{en} is not a motion intent."
    if reason == "skill_has_no_behavior":
        return f"{de} ist kein benanntes Verhalten.", f"{en} is not a named behavior."
    what = why.get(reason, ("abgelehnt", "refused"))
    return (
        f"{de} nicht gesendet: {what[0]}{f' ({detail[0]})' if detail[0] else ''}.",
        f"{en} not sent: {what[1]}{f' ({detail[1]})' if detail[1] else ''}.",
    )


def ai_key_saved(label: str) -> Bilingual:
    return f"Schlüssel für {label} geprüft und gespeichert.", f"Key for {label} checked and saved."


def ai_key_removed(label: str) -> Bilingual:
    return f"Schlüssel für {label} entfernt.", f"Key for {label} removed."


def people_model_missing() -> Bilingual:
    return (
        "Die echte Ente sucht Menschen, aber die Personenerkennung ist noch nicht geladen "
        "(Tab „KI-Anbieter“). Bis dahin findet sie nur die Markierung der Simulation.",
        "The real duck looks for people, but the person detector is not loaded yet (the “AI "
        "vendors” tab). Until then it only finds the simulation's marker.",
    )


def people_model_ready() -> Bilingual:
    return (
        "Personenerkennung geladen: erkennt Menschen auf diesem Rechner.",
        "Person detector loaded: finds people on this computer.",
    )


def planner_asked(label: str) -> Bilingual:
    return f"{label} entwirft einen Ablauf …", f"{label} is drafting a behavior …"


def planner_drafted(label: str, name: str) -> Bilingual:
    return (
        f"Entwurf von {label}: „{name}“. Prüfe ihn, bevor du speicherst.",
        f"Draft by {label}: “{name}”. Check it before you save.",
    )


def planner_failed(label: str) -> Bilingual:
    return (
        f"{label} hat keinen brauchbaren Entwurf geliefert.",
        f"{label} did not come up with a usable draft.",
    )


def stuck() -> Bilingual:
    return (
        "Die Ente tritt auf der Stelle: Befehle kommen an, aber sie kommt nicht voran.",
        "The duck is stepping in place: the commands arrive, but it is not getting anywhere.",
    )


def moving_again() -> Bilingual:
    return "Die Ente kommt wieder voran.", "The duck is moving again."


def battery_percent(level: float) -> Bilingual:
    percent = f"{round(level * 100)} %"
    return f"Akku {percent}", f"battery {percent}"


def behavior_sent(skill: Text) -> Bilingual:
    de, en = name_of(skill)
    return f"{de} gestartet.", f"{en} started."


def emergency_stop() -> Bilingual:
    return "Notstopp: Ente angehalten.", "Emergency stop: the duck was stopped."


def watchdog_tripped() -> Bilingual:
    return (
        "Der Ablauf hat ausgesetzt: Ente angehalten.",
        "The behavior went quiet: the duck was stopped.",
    )


def went_quiet(silent_s: float) -> Bilingual:
    return f"hat {silent_s:.1f} s ausgesetzt", f"went quiet for {silent_s:.1f} s"


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
    de, en = _backend_subject(kind)
    return f"{de} verbunden.", f"{en} connected."


def backend_unavailable(kind: str, host: str = "") -> Bilingual:
    de, en = _backend_subject(kind)
    hint: Bilingual = ("", "")
    if kind == "sim":
        hint = (" Starte sie mit sim/up.sh.", " Start it with sim/up.sh.")
    elif kind == "duck":
        command = f"scripts/duck-tunnel.sh {host or '<ente>'}"
        hint = (f" Öffne zuerst den Tunnel: {command}", f" Open the tunnel first: {command}")
    return f"{de} nicht erreichbar.{hint[0]}", f"{en} is not reachable.{hint[1]}"


def backend_switched(kind: str) -> Bilingual:
    de, en = backend(kind)
    return f"Gewechselt zu: {de}.", f"Switched to {en}."


def backend_lost(kind: str, error: str) -> Bilingual:
    de, en = _backend_subject(kind)
    return f"{de}: Verbindung verloren ({error}).", f"{en}: connection lost ({error})."

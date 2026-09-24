# ADR-0010: A local person detector, YOLOX-nano, fetched on a click

- Status: accepted
- Date: 2026-09-24

## Context

§4 asks for two clock rates: local detectors at 10–30 Hz for steering, a model at 0.5–2 Hz for
questions. Until now the local half only knew markers: the magenta pillar of the simulation and
the practice duck's drawn legs. Nothing on the real duck would find a real person — upstream's
`duck-detect` and `pngwn/microduck-detector` find ducks (docs/upstream-notes.md) — and a vendor
model (ADR-0009) answers about once a second, too slowly to keep a walking duck pointed at
someone.

## Decision

1. **YOLOX-nano through onnxruntime** (`runtime/duckstudio/perception/person_yolox.py`):
   Megvii's `yolox_nano.onnx`, release 0.1.1rc0, Apache-2.0, 3.66 MB, COCO class 0. About
   20 ms a frame on a laptop CPU with two threads; the perception service runs it with
   `asyncio.to_thread`, off the loop the executor ticks on. `onnxruntime` is a dependency.
2. **Not in the repository, fetched on a click.** The „KI-Anbieter" tab has a card „Personen-
   erkennung auf diesem Rechner" with „Personenerkennung laden (3,7 MB)". The runtime downloads
   the file into `~/.cache/duckstudio/models/` (or `$DUCKSTUDIO_MODELS`), checks the SHA-256
   pinned in the code, and keeps it only if it matches. Tests never see a downloaded model.
3. **Automatic by backend.** The real duck gets the model; the simulation keeps its marker
   detector, the practice duck its own — the model finds neither (checked: score 0.00 on the
   rendered legs). Without the model, the real duck falls back to the marker detector and the
   log says what to load. „Immer" puts the model on every backend, for trying it out.
4. **Same output as the other detectors.** The biggest person is the nearest one; its box
   centre gives the bearing with the same optics, the ToF gives the range, a shoulder width of
   0.45 m the fallback. `perceive: person.nearest` and `direction: toward_person` do not change.

The pre-processing is the one the file answers to, measured, not the one in the YOLOX source at
that tag: that `preproc` normalises with ImageNet mean/std, and the released file then scores
nothing above 0.01. Raw 0–255 BGR, letterboxed into 416×416 with grey 114, gives a person at
0.93 on the repo's `assets/sunjian.png` and dog 0.83 / car 0.81 / bicycle 0.81 (no person) on
`assets/dog.jpg`.

## Alternatives considered

- **Only vendor models (ADR-0009).** Good at questions, too slow and too costly to steer by,
  and every frame leaves the machine.
- **Ultralytics YOLO11 / `pngwn/microduck-detector`.** AGPL, and it finds ducks.
- **Bigger YOLOX (tiny, 20 MB) or RT-DETR.** Better at a distance; nano is enough for a person
  one to three metres from a duck, and five times smaller to fetch. The slot takes any of them.
- **Ship the model in the repo.** 3.7 MB of binary in every clone, for a feature that only
  matters on the real duck; the click keeps it where it is used.
- **Download on start-up.** A runtime that fetches files by itself is a runtime that surprises
  someone; a click with the size on the button does not.

## Consequences

- „Folge mir" finds real people on the real duck as soon as the model is loaded, at the local
  rate; „Folge mir (mit KI)" stays for when a model should decide who the person is.
- The simulation and the practice duck cannot exercise the model — they have no people. Its
  real test is M4, with the duck's own camera (docs/m4-hardware-checklist.md).
- The head camera sits 20 cm off the floor: close up, a person is legs. How well nano finds
  legs from below is the open question for December; the next step if it does not is YOLOX-tiny
  behind the same slot.

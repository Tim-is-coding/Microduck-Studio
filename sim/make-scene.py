#!/usr/bin/env python3
"""Generate the follow-me scene: upstream `scene.xml` plus a marked "person".

MuJoCo resolves `<include>` and asset paths relative to the top-level model file, so a scene
that reuses upstream's robot has to live in upstream's scene directory. This writes
`scene_studio_follow_me.xml` next to `scene.xml` inside the (git-ignored) microduck_rl checkout
and prints its path. Nothing upstream is modified; the file is regenerated on every start.

The person is a magenta cylinder, 1.2 m tall, standing `STUDIO_PERSON_X` metres ahead and
`STUDIO_PERSON_Y` metres to the left of the duck's start (x forward, y left). Magenta because
nothing else in the rendered scene is (blue floor, grey duck, gradient sky), so the local
detector in `duckstudio.perception.person_local` can find it by colour alone (M2). The
cylinder collides, so the simulated ToF sees it too.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENES = HERE / "upstream-rl" / "src" / "mjlab_microduck" / "robot" / "microduck"
SOURCE = SCENES / "scene.xml"
TARGET = SCENES / "scene_studio_follow_me.xml"

PERSON_X = float(os.environ.get("STUDIO_PERSON_X", "1.5"))
PERSON_Y = float(os.environ.get("STUDIO_PERSON_Y", "0.0"))
PERSON_HEIGHT = 1.2
PERSON_RADIUS = 0.12
PERSON_RGBA = "1 0 1 1"


def main() -> int:
    if not SOURCE.exists():
        print(f"no upstream scene at {SOURCE} — run sim/fetch-upstream.sh", file=sys.stderr)
        return 1
    tree = ET.parse(SOURCE)
    root = tree.getroot()
    root.set("model", "studio_follow_me")
    world = root.find("worldbody")
    if world is None:
        print("upstream scene.xml has no <worldbody>", file=sys.stderr)
        return 1
    person = ET.SubElement(world, "body", name="person", pos=f"{PERSON_X} {PERSON_Y} {PERSON_HEIGHT / 2}")
    ET.SubElement(
        person,
        "geom",
        name="person_marker",
        type="cylinder",
        size=f"{PERSON_RADIUS} {PERSON_HEIGHT / 2}",
        rgba=PERSON_RGBA,
    )
    # A "head" so the silhouette reads as a person from the duck's low camera.
    ET.SubElement(
        person,
        "geom",
        name="person_head",
        type="sphere",
        size="0.11",
        pos=f"0 0 {PERSON_HEIGHT / 2 + 0.11}",
        rgba=PERSON_RGBA,
    )
    ET.indent(tree, space="    ")
    tree.write(TARGET, encoding="unicode", xml_declaration=False)
    print(TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())

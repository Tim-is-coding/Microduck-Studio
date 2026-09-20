import { describe, expect, it } from "vitest";

import {
  TOF_NEAR_M,
  closestZone,
  formatDistance,
  layoutMarkers,
  marker,
  proximity,
  shortLabel,
  tagBox,
  zoneColor,
} from "../src/live/overlay";
import { setLanguage } from "../src/i18n";
import type { PersonDetection } from "../src/schemas";

const seen = (over: Partial<PersonDetection> = {}): PersonDetection => ({
  timestamp: 1,
  bearing_rad: 0.2,
  distance_m: 1.5,
  pixel_x: 90,
  pixel_y: 320,
  frame_width: 360,
  frame_height: 640,
  area_px: 500,
  confidence: 0.9,
  ...over,
});

describe("markers sit where the runtime saw the thing", () => {
  it("turns frame pixels into fractions of the picture", () => {
    const m = marker(seen(), "person", "Person");
    expect(m).toMatchObject({ x: 0.25, y: 0.5, kind: "person", label: "Person", labelDy: 0 });
  });

  it("has nothing to draw without a sighting or frame size", () => {
    expect(marker(null, "person", "Person")).toBeNull();
    expect(marker(seen({ frame_width: 0 }), "person", "Person")).toBeNull();
  });

  it("keeps a marker inside the picture even when the runtime is off by a pixel", () => {
    const m = marker(seen({ pixel_x: 400, pixel_y: -10 }), "target", "Ball");
    expect(m).toMatchObject({ x: 1, y: 0 });
  });

  it("shortens a question to a tag", () => {
    expect(shortLabel("Ball")).toBe("Ball");
    expect(shortLabel("Wo ist der rote Ball?")).toBe("Wo ist der rote…");
    expect(shortLabel("Wo ist der rote Ball?").length).toBeLessThanOrEqual(16);
  });

  it("pushes two tags apart when both point at the same spot", () => {
    const person = marker(seen(), "person", "Person")!;
    const target = marker(seen(), "target", "Ball")!;
    const [a, b] = layoutMarkers([person, target]);
    expect(a!.labelDy).toBe(0);
    expect(b!.labelDy).toBeGreaterThan(0);
  });

  it("leaves tags alone when the things are far apart", () => {
    const person = marker(seen({ pixel_x: 20 }), "person", "Person")!;
    const target = marker(seen({ pixel_x: 340 }), "target", "Ball")!;
    expect(layoutMarkers([person, target]).every((m) => m.labelDy === 0)).toBe(true);
  });
});

describe("a tag stays inside the frame", () => {
  it("sits to the right when there is room", () => {
    const { x, width } = tagBox(50, "Person", 20, 30, 360);
    expect(x).toBe(80);
    expect(x + width).toBeLessThan(360);
  });

  it("flips to the left near the right edge", () => {
    const { x, width } = tagBox(330, "Person", 20, 30, 360);
    expect(x + width).toBeLessThanOrEqual(330);
  });

  it("is pinned inside when neither side has room", () => {
    const { x, width } = tagBox(200, "Person", 20, 30, 240);
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x + width).toBeLessThanOrEqual(240);
  });

  it("pins a tag wider than the picture to the left edge", () => {
    expect(tagBox(30, "Wo ist der rote…", 20, 30, 120).x).toBe(0);
  });
});

describe("ToF zones", () => {
  it("is 0 at touching distance and 1 when the way is clear", () => {
    expect(proximity(0.1)).toBe(0);
    expect(proximity(TOF_NEAR_M)).toBe(0);
    expect(proximity(3.9)).toBe(1);
    expect(proximity(1.2)).toBeGreaterThan(0);
    expect(proximity(1.2)).toBeLessThan(1);
  });

  it("colours near zones warm and far ones quiet, in both themes", () => {
    expect(zoneColor(0.2)).not.toBe(zoneColor(3.0));
    expect(zoneColor(0.2)).toMatch(/^hsl\(/);
    const lightness = (c: string) => Number(/ ([\d.]+)%\)$/.exec(c)![1]);
    expect(lightness(zoneColor(3.0))).toBeGreaterThan(lightness(zoneColor(0.2))); // pale on paper
    expect(lightness(zoneColor(3.0, true))).toBeLessThan(lightness(zoneColor(0.2, true))); // dark at night
  });

  it("finds the closest zone straight ahead, ignoring sky and floor", () => {
    const rows = Array.from({ length: 8 }, () => Array.from({ length: 8 }, () => 3.9));
    rows[0]![3] = 0.3; // sky row: not in the way
    rows[7]![4] = 0.4; // floor row: not in the way
    rows[2]![0] = 0.2; // far left: not straight ahead
    rows[4]![4] = 1.1;
    expect(closestZone(rows)).toEqual({ row: 4, col: 4, distanceM: 1.1 });
    expect(closestZone(null)).toBeNull();
  });
});

describe("distances read like the language they are shown in", () => {
  it("uses a comma in German and a dot in English", () => {
    setLanguage("de");
    expect(formatDistance(1.25)).toBe("1,3 m");
    setLanguage("en");
    expect(formatDistance(1.25)).toBe("1.3 m");
    expect(formatDistance(null)).toBe("");
    setLanguage("de");
  });
});

/**
 * Pure geometry and colour for the live view. No React, so what the overlay claims about
 * the world can be unit-tested: a marker sits where the runtime says the thing was, and a
 * ToF zone is coloured by how close it is.
 */
import type { PersonDetection, TargetSighting } from "../schemas";

export const TOF_NEAR_M = 0.25; // the walk manifest stops here (skills/walk.skill.yaml)
export const TOF_FAR_M = 2.5; // beyond this a zone is "frei"
export const TOF_RANGE_M = 3.9; // the sensor's own limit: nothing there

export interface Marker {
  x: number; // 0..1 of the frame width
  y: number; // 0..1 of the frame height
  /** A word or two on the picture; distance and bearing are in the chips below it. */
  label: string;
  kind: "person" | "target";
  /** Vertical nudge for the tag, in "short edge percent", set by `layoutMarkers`. */
  labelDy: number;
}

const LABEL_MAX = 16;

/** A question can be a whole sentence; the picture has room for a few words. */
export function shortLabel(text: string, max = LABEL_MAX): string {
  const clean = text.trim();
  return clean.length <= max ? clean : `${clean.slice(0, max - 1).trimEnd()}…`;
}

/**
 * Two markers on the same spot (the mock's bar is both "person" and "target") would draw
 * their labels on top of each other. Push them apart instead of hiding one.
 */
export function layoutMarkers(markers: Marker[]): Marker[] {
  const out: Marker[] = [];
  for (const m of markers) {
    const previous = out[out.length - 1];
    const overlaps =
      previous !== undefined &&
      Math.abs(m.x - previous.x) < 0.12 &&
      Math.abs(m.y - previous.y) < 0.12;
    out.push(overlaps ? { ...m, labelDy: previous.labelDy + 16 } : m);
  }
  return out;
}

export function degrees(bearingRad: number): number {
  return Math.round(Math.abs((bearingRad * 180) / Math.PI));
}

export function formatDistance(distanceM: number | null | undefined): string {
  if (distanceM == null) return "";
  return `${distanceM.toFixed(distanceM < 10 ? 1 : 0).replace(".", ",")} m`;
}

/** Where a sighting sits in the frame, as a fraction — the image may be scaled anywhere. */
export function marker(
  sighting: (PersonDetection | TargetSighting) | null | undefined,
  kind: Marker["kind"],
  label: string,
): Marker | null {
  if (!sighting || !sighting.frame_width || !sighting.frame_height) return null;
  return {
    x: clamp01(sighting.pixel_x / sighting.frame_width),
    y: clamp01(sighting.pixel_y / sighting.frame_height),
    kind,
    label: shortLabel(label),
    labelDy: 0,
  };
}

/**
 * Where a tag fits next to its crosshair: to the right when there is room, otherwise to the
 * left, and pinned inside the frame when neither side has enough. Widths are estimated from
 * the character count — good enough for one word, and it needs no layout pass in the DOM.
 */
export function tagBox(
  x: number,
  label: string,
  fontSize: number,
  gap: number,
  frameWidth: number,
): { x: number; width: number } {
  const width = (label.length * 0.58 + 1.0) * fontSize;
  const right = x + gap;
  const left = x - gap - width;
  const raw = right + width <= frameWidth || left < 0 ? right : left;
  const margin = 0.5 * fontSize;
  // A tag wider than the picture cannot fit; pin it left and let the edge cut it off.
  const maxX = Math.max(0, frameWidth - width - margin);
  return { x: Math.min(Math.max(margin, raw), maxX), width };
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

/** 0 (touching) … 1 (far away or empty), for colouring a ToF zone. */
export function proximity(distanceM: number): number {
  if (!Number.isFinite(distanceM) || distanceM >= TOF_RANGE_M) return 1;
  if (distanceM <= TOF_NEAR_M) return 0;
  return clamp01((distanceM - TOF_NEAR_M) / (TOF_FAR_M - TOF_NEAR_M));
}

/** Warm where something is close, pale where the way is clear. */
export function zoneColor(distanceM: number): string {
  const p = proximity(distanceM);
  const hue = 8 + p * 40; // red → sand
  const light = 42 + p * 46;
  const sat = 78 - p * 55;
  return `hsl(${hue.toFixed(0)} ${sat.toFixed(0)}% ${light.toFixed(0)}%)`;
}

export interface ZoneStat {
  row: number;
  col: number;
  distanceM: number;
}

/** The closest zone the duck would walk into: centre columns, ignoring sky and floor rows. */
export function closestZone(rows: readonly (readonly number[])[] | null | undefined): ZoneStat | null {
  if (!rows || rows.length === 0) return null;
  let best: ZoneStat | null = null;
  rows.forEach((row, r) => {
    if (r === 0 || r === rows.length - 1) return; // sky and floor
    row.forEach((distanceM, c) => {
      if (c < 3 || c > 4) return; // straight ahead
      if (distanceM <= 0.05 || distanceM >= TOF_RANGE_M) return;
      if (!best || distanceM < best.distanceM) best = { row: r, col: c, distanceM };
    });
  });
  return best;
}

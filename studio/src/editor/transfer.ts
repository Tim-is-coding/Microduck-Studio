/**
 * Copying a behavior, taking it out of the Studio and bringing one back.
 *
 * Hub sharing waits for hardware (CLAUDE.md §8, M4), but a behavior still has to be able to
 * leave this machine: a file is the simplest way, and it is the same YAML the runtime writes.
 * Nothing here writes anything — a copy and an imported file open as a *draft*, so the pack
 * goes through the editor, the live validation and Speichern like everything else. An
 * imported file is data, never an instruction: it is parsed, schema-checked and given a free
 * id before it is allowed anywhere near the runtime.
 */
import { parse, stringify } from "yaml";

import type { Language } from "../i18n";
import { BehaviorPack } from "../schemas";
import { tidy } from "./model";

/** Names are content, so each language the pack carries gets its own suffix. */
export const COPY_SUFFIX: Record<Language, string> = { de: "(Kopie)", en: "(copy)" };

/** `folge-mir-copy`, `folge-mir-copy-2`, … — ids stay English and never collide (§3.7). */
export function freeId(wanted: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  if (!used.has(wanted)) return wanted;
  for (let n = 2; ; n++) {
    const candidate = `${wanted}-${n}`;
    if (!used.has(candidate)) return candidate;
  }
}

export function duplicate(pack: BehaviorPack, taken: Iterable<string>): BehaviorPack {
  const name = { de: `${pack.name.de} ${COPY_SUFFIX.de}`, ...(pack.name.en ? { en: `${pack.name.en} ${COPY_SUFFIX.en}` } : {}) };
  return { ...tidy(pack), id: freeId(`${pack.id}-copy`, taken), name };
}

export function toYaml(pack: BehaviorPack): string {
  return stringify(tidy(pack));
}

export function fileName(pack: BehaviorPack): string {
  return `${pack.id}.behavior.yaml`;
}

export type ImportResult =
  | { ok: true; pack: BehaviorPack; renamedFrom: string | null }
  | { ok: false; reason: "yaml" | "schema"; detail: string };

/** Turn the text of a file into a draft, or say what is wrong with it. */
export function fromYaml(text: string, taken: Iterable<string>): ImportResult {
  let data: unknown;
  try {
    data = parse(text);
  } catch (e) {
    return { ok: false, reason: "yaml", detail: e instanceof Error ? e.message.split("\n")[0]! : String(e) };
  }
  const parsed = BehaviorPack.safeParse(data);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return { ok: false, reason: "schema", detail: first ? `${first.path.join(".") || "?"}: ${first.message}` : "?" };
  }
  const id = freeId(parsed.data.id, taken);
  return { ok: true, pack: { ...parsed.data, id }, renamedFrom: id === parsed.data.id ? null : parsed.data.id };
}

/** Hand a file to the browser. Nothing leaves the machine: this is a local download. */
export function download(name: string, text: string): void {
  if (typeof document === "undefined") return;
  const url = URL.createObjectURL(new Blob([text], { type: "application/yaml" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  // Revoking in the same tick cancels the download in some browsers; let it start first.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

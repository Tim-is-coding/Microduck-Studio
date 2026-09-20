/**
 * Starter behaviors for an empty Studio. The first screen of a fresh install has nothing on
 * it but a dashed card, and "leere Schrittliste" is a poor first lesson — these give one
 * click to a complete, runnable Ablauf you can read, change and start (§3.1, M3).
 *
 * A template is data, not a file: it is offered only while the list is empty, it is not saved
 * until you press Speichern, and every skill it names must be in the registry — a Studio
 * without the `walk` manifest simply does not offer the template that walks.
 */
import type { BehaviorPack, SkillManifest, Step } from "../schemas";
import { BEHAVIOR_SCHEMA_ID, defaultWith } from "./model";

export interface Template {
  /** What the chip says, in both languages — template texts are content, not UI chrome. */
  name: { de: string; en: string };
  /** Skills and behaviors the pack names; the template is hidden if one is missing. */
  needs: readonly string[];
  pack: BehaviorPack;
}

const TEMPLATES: readonly Template[] = [
  {
    name: { de: "Begrüßung", en: "Greeting" },
    needs: ["quack", "sit", "look_around", "getup"],
    pack: {
      schema: BEHAVIOR_SCHEMA_ID,
      id: "begruessung",
      name: { de: "Begrüßung", en: "Greeting" },
      summary: {
        de: "Die Ente sucht eine Person, quakt einmal und setzt sich hin.",
        en: "The duck looks for a person, quacks once and sits down.",
      },
      trigger: { kind: "manual" },
      steps: [
        { perceive: "person.nearest", on_none: { do: "look_around", seconds: 5, then: "continue" } },
        { skill: "quack", with: { style: "short" } },
        { skill: "sit", with: {} },
      ],
      always: [{ on: "fallen", do: ["getup", "resume"] }],
    },
  },
  {
    name: { de: "Folge mir", en: "Follow me" },
    needs: ["walk", "quack", "look_around", "getup"],
    pack: {
      schema: BEHAVIOR_SCHEMA_ID,
      id: "folge-mir",
      name: { de: "Folge mir", en: "Follow me" },
      summary: {
        de: "Die Ente läuft der nächsten Person nach, bis du „Stopp“ sagst.",
        en: "The duck follows the nearest person until you say stop.",
      },
      trigger: { kind: "speech", phrases: { de: ["Folge mir", "Komm mit"], en: ["Follow me"] } },
      steps: [
        { perceive: "person.nearest", on_none: { do: "look_around", seconds: 5, then: "retry" } },
        {
          skill: "walk",
          with: { direction: "toward_person", tempo: "easy", distance: 60 },
          until: { any: [{ speech: { de: ["Stopp"], en: ["Stop"] } }, { elapsed: "10m" }] },
        },
        { skill: "quack", with: { style: "short" } },
      ],
      always: [{ on: "fallen", do: ["getup", "resume"] }],
    },
  },
];

/** The templates this Studio can actually build, with every skill card filled from its
 *  manifest — a template carries the choices that make it interesting, the manifest the rest. */
export function templatesFor(skills: Map<string, SkillManifest>): Template[] {
  return TEMPLATES.filter((tpl) => tpl.needs.every((id) => skills.has(id))).map((tpl) => ({
    ...tpl,
    pack: { ...tpl.pack, steps: tpl.pack.steps.map((step) => fill(step, skills)) },
  }));
}

function fill(step: Step, skills: Map<string, SkillManifest>): Step {
  if (!("skill" in step)) return step;
  const manifest = skills.get(step.skill);
  return manifest ? { ...step, with: { ...defaultWith(manifest), ...step.with } } : step;
}

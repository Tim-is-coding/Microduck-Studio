import { phrases as phraseList } from "../i18n";
import type { BehaviorPack } from "../schemas";

/** Trigger phrases and every `until: speech` phrase: what the microphone should listen for. */
export function packPhrases(pack: BehaviorPack): string[] {
  const out = pack.trigger.kind === "speech" ? [...phraseList(pack.trigger.phrases)] : [];
  for (const step of pack.steps) {
    const until = "until" in step ? step.until : null;
    for (const c of [...(until?.any ?? []), ...(until?.all ?? [])]) {
      if ("speech" in c) out.push(...phraseList(c.speech));
    }
  }
  return [...new Set(out)];
}

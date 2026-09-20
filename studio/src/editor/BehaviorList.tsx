import { t } from "../i18n";
import type { BehaviorPackFromApi } from "../schemas";

interface Props {
  behaviors: BehaviorPackFromApi[];
  connected: boolean;
  running: boolean;
  onOpen: (id: string) => void;
  onRun: (id: string) => void;
  onNew: () => void;
}

/**
 * The first thing the Studio shows: every behavior as a card you can read, open or start,
 * and an empty one that makes a new behavior. §3.1 — nobody has to know what a file is.
 */
export function BehaviorList({ behaviors, connected, running, onOpen, onRun, onNew }: Props) {
  return (
    <div className="behavior-list">
      {behaviors.map((b) => (
        <article className="behavior-card" key={b.id}>
          <button className="open" onClick={() => onOpen(b.id)} type="button">
            <span className="title">{b.name.de}</span>
            {b.summary?.de && <span className="sub">{b.summary.de}</span>}
          </button>
          <div className="chips">
            <span className="chip">{describeTrigger(b)}</span>
            <span className="chip">{t("list.steps", { count: b.steps.length })}</span>
            {b.vlm && <span className="chip ki">{t("list.vlm", { provider: b.vlm.provider })}</span>}
            {b.problems.length > 0 && <span className="chip problem">{t("list.problems", { count: b.problems.length })}</span>}
          </div>
          <div className="actions">
            <button className="btn" onClick={() => onOpen(b.id)} type="button">{t("list.open")}</button>
            <button
              className="btn primary"
              disabled={!connected || running || b.problems.length > 0}
              onClick={() => onRun(b.id)}
              type="button"
            >
              ▶ {t("run.start")}
            </button>
          </div>
        </article>
      ))}
      <button className="behavior-card new" onClick={onNew} type="button">
        <span className="plus" aria-hidden="true">+</span>
        <span className="title">{t("list.new")}</span>
        <span className="sub">{t("list.new.hint")}</span>
      </button>
    </div>
  );
}

function describeTrigger(behavior: BehaviorPackFromApi): string {
  if (behavior.trigger.kind === "speech") return `„${behavior.trigger.phrases.de[0]}“`;
  return t("editor.trigger.kind.manual");
}

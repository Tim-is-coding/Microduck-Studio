import { phrases as phraseList, quote, t, text } from "../i18n";
import type { BehaviorPack, BehaviorPackFromApi } from "../schemas";
import { Icon } from "../ui/Icon";
import type { Template } from "./templates";

interface Props {
  behaviors: BehaviorPackFromApi[];
  connected: boolean;
  running: boolean;
  templates: Template[];
  onOpen: (id: string) => void;
  onRun: (id: string) => void;
  onNew: () => void;
  onTemplate: (pack: BehaviorPack) => void;
}

/**
 * The first thing the Studio shows: every behavior as a card you can read, open or start,
 * and an empty one that makes a new behavior. §3.1 — nobody has to know what a file is.
 */
export function BehaviorList({ behaviors, connected, running, templates, onOpen, onRun, onNew, onTemplate }: Props) {
  return (
    <>
    <div className="behavior-list">
      {behaviors.map((b) => (
        <article className="behavior-card" key={b.id}>
          <button className="open" onClick={() => onOpen(b.id)} type="button">
            <span className="title">{text(b.name)}</span>
            {b.summary && <span className="sub">{text(b.summary)}</span>}
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
              <Icon name="play" /> {t("run.start")}
            </button>
          </div>
        </article>
      ))}
      <button className="behavior-card new" onClick={onNew} type="button">
        <span className="plus"><Icon name="plus" size={1.4} /></span>
        <span className="title">{t("list.new")}</span>
        <span className="sub">{t("list.new.hint")}</span>
      </button>
    </div>
    {behaviors.length === 0 && templates.length > 0 && (
      <div className="starters">
        <span className="label">{t("list.templates")}</span>
        {templates.map((tpl) => (
          <button className="chip clickable" key={tpl.pack.id} onClick={() => onTemplate(tpl.pack)} type="button">
            <Icon name="plus" size={0.9} /> {text(tpl.name)}
          </button>
        ))}
        <span className="sub">{t("list.templates.hint")}</span>
      </div>
    )}
    </>
  );
}

function describeTrigger(behavior: BehaviorPackFromApi): string {
  if (behavior.trigger.kind === "speech") return quote(phraseList(behavior.trigger.phrases)[0] ?? "");
  return t("editor.trigger.kind.manual");
}

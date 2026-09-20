import { useRef, useState } from "react";

import { phrases as phraseList, quote, t, text } from "../i18n";
import type { BehaviorPack, BehaviorPackFromApi } from "../schemas";
import { Icon } from "../ui/Icon";
import type { Template } from "./templates";
import { download, duplicate, fileName, fromYaml, toYaml } from "./transfer";

interface Props {
  behaviors: BehaviorPackFromApi[];
  connected: boolean;
  running: boolean;
  templates: Template[];
  onOpen: (id: string) => void;
  onRun: (id: string) => void;
  onNew: () => void;
  /** A pack that is not saved yet: a template, a copy, a file. It opens in the editor, with
   *  a note for anything the Studio had to change on the way in. */
  onDraft: (pack: BehaviorPack, notice?: string) => void;
}

/**
 * The first thing the Studio shows: every behavior as a card you can read, open, start, copy
 * or take with you, and an empty one that makes a new behavior. §3.1 — nobody has to know
 * what a file is, but a file is how a behavior travels until the Hub path exists (M4).
 */
export function BehaviorList({ behaviors, connected, running, templates, onOpen, onRun, onNew, onDraft }: Props) {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [notice, setNotice] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const taken = behaviors.map((b) => b.id);

  async function readFile(file: File) {
    const result = fromYaml(await file.text(), taken);
    if (!result.ok) {
      setNotice({ kind: "error", text: t(`list.import.${result.reason}`, { detail: result.detail }) });
      return;
    }
    setNotice(null);
    onDraft(
      result.pack,
      result.renamedFrom ? t("list.import.renamed", { from: result.renamedFrom, to: result.pack.id }) : undefined,
    );
  }

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
              <span className="spacer" />
              <button className="btn icon-only" onClick={() => onDraft(duplicate(b, taken))} title={t("list.duplicate")} type="button">
                <Icon name="copy" title={t("list.duplicate")} />
              </button>
              <button className="btn icon-only" onClick={() => download(fileName(b), toYaml(b))} title={t("list.export")} type="button">
                <Icon name="download" title={t("list.export")} />
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

      <div className="starters">
        {behaviors.length === 0 && templates.length > 0 && (
          <>
            <span className="label">{t("list.templates")}</span>
            {templates.map((tpl) => (
              <button className="chip clickable" key={tpl.pack.id} onClick={() => onDraft(structuredClone(tpl.pack))} type="button">
                <Icon name="plus" size={0.9} /> {text(tpl.name)}
              </button>
            ))}
          </>
        )}
        <button className="chip clickable" onClick={() => fileInput.current?.click()} type="button">
          <Icon name="upload" size={0.9} /> {t("list.import")}
        </button>
        <input
          accept=".yaml,.yml,application/yaml,text/yaml"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = ""; // the same file may be picked again after a fix
            if (file) void readFile(file);
          }}
          ref={fileInput}
          type="file"
        />
        <span className="sub">{behaviors.length === 0 ? t("list.templates.hint") : t("list.import.hint")}</span>
        {notice && <span className={`sub notice ${notice.kind}`}>{notice.text}</span>}
      </div>
    </>
  );
}

function describeTrigger(behavior: BehaviorPackFromApi): string {
  if (behavior.trigger.kind === "speech") return quote(phraseList(behavior.trigger.phrases)[0] ?? "");
  return t("editor.trigger.kind.manual");
}

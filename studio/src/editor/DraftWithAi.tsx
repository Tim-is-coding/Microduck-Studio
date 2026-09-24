import { useEffect, useState } from "react";

import { t, tOr } from "../i18n";
import { BehaviorPack } from "../schemas";
import { useStudio } from "../store/useStudio";

interface Props {
  /** Opens the draft in the editor; nothing is saved until the person presses Speichern. */
  onDraft: (pack: BehaviorPack, notice: string) => void;
  onSetUp: () => void;
}

const REASONS = new Set(["no_key", "invalid", "refused", "unreachable", "vendor", "empty", "too_long", "empty_description"]);

/**
 * „Mit KI entwerfen" (ADR-0011): a sentence in, a draft in the editor out. The model only drafts;
 * the person reads every step, changes what is wrong and saves — or throws it away.
 */
export function DraftWithAi({ onDraft, onSetUp }: Props) {
  const { ai, loadAi } = useStudio();
  const [text, setText] = useState("");
  const [vendor, setVendor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!ai) void loadAi();
  }, [ai, loadAi]);

  const ready = (ai?.vendors ?? []).filter((v) => v.key);
  const chosen = vendor && ready.some((v) => v.id === vendor) ? vendor : ready[0]?.id;

  const submit = async () => {
    if (!text.trim() || !chosen) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/planner/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: text.trim(), vendor: chosen }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const reason = body?.detail?.reason;
        setError(typeof reason === "string" && REASONS.has(reason) ? reason : "failed");
        return;
      }
      const parsed = BehaviorPack.safeParse(body?.draft);
      if (!parsed.success) {
        setError("invalid");
        return;
      }
      onDraft(parsed.data, t("draft.notice", { vendor: body.label ?? chosen }));
      setText("");
    } catch {
      setError("unreachable");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card aidraft">
      <div className="title">{t("draft.title")}</div>
      <p className="sub">{t("draft.lead")}</p>
      {ready.length === 0 ? (
        <p className="sub">
          {t("draft.nokey")}{" "}
          <button className="btn small" onClick={onSetUp} type="button">{t("draft.setup")}</button>
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label className="sr" htmlFor="draft-text">{t("draft.title")}</label>
          <textarea
            disabled={busy}
            id="draft-text"
            maxLength={1000}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("draft.placeholder")}
            rows={3}
            value={text}
          />
          <div className="row">
            {ready.length > 1 && (
              <select aria-label={t("draft.vendor")} onChange={(e) => setVendor(e.target.value)} value={chosen}>
                {ready.map((v) => (
                  <option key={v.id} value={v.id}>{tOr(`vlm.provider.${v.id}`, v.label)}</option>
                ))}
              </select>
            )}
            <button className="btn primary" disabled={busy || !text.trim()} type="submit">
              {busy ? t("draft.busy", { vendor: tOr(`vlm.provider.${chosen}`, chosen ?? "") }) : t("draft.go")}
            </button>
          </div>
        </form>
      )}
      {error && <p className="error" role="alert">{t(`draft.error.${error}`)}</p>}
    </section>
  );
}

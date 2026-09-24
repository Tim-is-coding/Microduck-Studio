import { useEffect, useState } from "react";

import { formatDate, language, number, t } from "../i18n";
import type { AiVendor, LocalDetector } from "../schemas";
import { useStudio } from "../store/useStudio";

/**
 * KI-Anbieter (ADR-0009): bring a key, pick a model, see what it costs and where pictures go.
 *
 * The key field only ever sends; nothing the runtime returns contains a key, so there is
 * nothing here that could show one. A key is checked with the vendor before it is kept.
 */
export function AiVendors({ offline }: { offline: boolean }) {
  const { ai, loadAi } = useStudio();
  useEffect(() => {
    void loadAi();
  }, [loadAi]);

  if (offline) return <p className="empty">{t("ai.offline")}</p>;
  if (!ai) return <p className="empty">{t("ai.loading")}</p>;
  return (
    <section className="aipage">
      <h2>{t("ai.title")}</h2>
      <p className="lead">{t("ai.lead")}</p>
      <div className="aiprivacy">
        <p>{t("ai.privacy.keys")}</p>
        <p>{t("ai.privacy.frames")}</p>
      </div>
      {ai.local && <LocalCard local={ai.local} />}
      <h3 className="aisub">{t("ai.vendors.title")}</h3>
      <div className="aivendors">
        {ai.vendors.map((v) => (
          <VendorCard key={v.id} vendor={v} />
        ))}
      </div>
      <p className="meta">
        {t("ai.checked", { date: formatDate(ai.checked) })} {t("ai.rate", { hz: ai.hz, calls: ai.max_calls })}
      </p>
    </section>
  );
}

const REASONS = new Set(["rejected", "model", "unreachable", "format", "unknown_model"]);

function VendorCard({ vendor }: { vendor: AiVendor }) {
  const { saveAiKey, removeAiKey, setAiModel } = useStudio();
  const lang = language();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(vendor.model);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setModel(vendor.model), [vendor.model]);

  const hasKey = vendor.key !== null;
  const save = async () => {
    const k = key.trim();
    if (!k) return;
    setBusy(true);
    setError(null);
    const reason = await saveAiKey(vendor.id, k, model);
    setBusy(false);
    if (reason === null) setKey("");
    else setError(REASONS.has(reason) ? reason : "failed");
  };
  const pickModel = (id: string) => {
    setModel(id);
    if (hasKey) void setAiModel(vendor.id, id);
  };

  return (
    <article className={`card aivendor${hasKey ? " on" : ""}`}>
      <header>
        <h3>{vendor.label}</h3>
        {vendor.recommended && <span className="chip good">{t("ai.recommended")}</span>}
        {vendor.free_tier && <span className="chip">{t("ai.free")}</span>}
        {hasKey && <span className="chip on">{t("ai.ready")}</span>}
      </header>
      <p className="note">{vendor.note[lang] ?? vendor.note.de}</p>
      <p className="links">
        <a href={vendor.key_url} rel="noreferrer" target="_blank">{t("ai.link.key")} ↗</a>
        <a href={vendor.pricing_url} rel="noreferrer" target="_blank">{t("ai.link.pricing")} ↗</a>
        <a href={vendor.docs_url} rel="noreferrer" target="_blank">{t("ai.link.docs")} ↗</a>
        {vendor.terms_url && <a href={vendor.terms_url} rel="noreferrer" target="_blank">{t("ai.link.terms")} ↗</a>}
      </p>

      <fieldset className="models">
        <legend>{t("ai.model")}</legend>
        {vendor.models.map((m) => (
          <label key={m.id}>
            <input checked={model === m.id} name={`model-${vendor.id}`} onChange={() => pickModel(m.id)} type="radio" />
            <code>{m.id}</code> <span className="sub">{m.note[lang] ?? m.note.de}</span>
          </label>
        ))}
      </fieldset>

      {hasKey ? (
        <div className="keyrow">
          <span>
            {vendor.key!.source === "studio"
              ? t("ai.key.stored", { hint: vendor.key!.hint })
              : t("ai.key.env", { hint: vendor.key!.hint, name: vendor.env_var })}
          </span>
          {vendor.key!.source === "studio" && (
            <button className="btn small" onClick={() => void removeAiKey(vendor.id)} type="button">{t("ai.key.remove")}</button>
          )}
        </div>
      ) : (
        <form
          className="keyrow"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label className="sr" htmlFor={`key-${vendor.id}`}>{t("ai.key.label", { vendor: vendor.label })}</label>
          <input
            autoComplete="off"
            disabled={busy}
            id={`key-${vendor.id}`}
            onChange={(e) => setKey(e.target.value)}
            placeholder={t("ai.key.placeholder")}
            spellCheck={false}
            type="password"
            value={key}
          />
          <button className="btn small primary" disabled={busy || !key.trim()} type="submit">
            {busy ? t("ai.key.checking") : t("ai.key.save")}
          </button>
        </form>
      )}
      {error && <p className="error" role="alert">{t(`ai.error.${error}`)}</p>}
    </article>
  );
}

/** YOLOX-nano on this machine: people, 10× a second, no picture leaving it (ADR-0010). */
function LocalCard({ local }: { local: LocalDetector }) {
  const { downloadPersonModel, setPersonMode } = useStudio();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const mb = number(local.bytes / 1_000_000, 1);
  const load = async () => {
    setBusy(true);
    setError(false);
    setError((await downloadPersonModel()) !== null);
    setBusy(false);
  };
  return (
    <article className={`card aivendor local${local.ready ? " on" : ""}`}>
      <header>
        <h3>{t("ai.local.title")}</h3>
        <span className="chip good">{t("ai.local.private")}</span>
        {local.ready && <span className="chip on">{t("ai.ready")}</span>}
      </header>
      <p className="note">{t("ai.local.note", { name: local.name, license: local.license })}</p>
      <fieldset className="models">
        <legend>{t("ai.local.where")}</legend>
        <label>
          <input checked={local.mode === "auto"} name="person-mode" onChange={() => void setPersonMode("auto")} type="radio" />
          <span>{t("ai.local.auto")}</span>
        </label>
        <label>
          <input checked={local.mode === "people"} name="person-mode" onChange={() => void setPersonMode("people")} type="radio" />
          <span>{t("ai.local.people")}</span>
        </label>
      </fieldset>
      {local.ready ? (
        <p className="keyrow">{t("ai.local.ready", { name: local.name })}</p>
      ) : (
        <div className="keyrow">
          <button className="btn small primary" disabled={busy} onClick={() => void load()} type="button">
            {busy ? t("ai.local.loading") : t("ai.local.load", { mb })}
          </button>
          <a href="https://github.com/Megvii-BaseDetection/YOLOX" rel="noreferrer" target="_blank">{t("ai.local.source")} ↗</a>
        </div>
      )}
      {error && <p className="error" role="alert">{t("ai.local.error")}</p>}
    </article>
  );
}

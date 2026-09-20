import { useState } from "react";

import { t, text } from "../i18n";
import type { HubPolicy, SkillManifest } from "../schemas";
import { Icon } from "../ui/Icon";

interface Props {
  skills: SkillManifest[];
  hubResults: HubPolicy[] | null;
  hubBusy: boolean;
  hubError: string | null;
  onSearch: (query: string) => void;
  onClear: () => void;
  onDetails: (repo: string) => Promise<HubPolicy | null>;
  onImport: (repo: string, slot: string) => void;
  onRemove: (id: string) => void;
}

/** The building blocks: what this Studio has, and what the Hub offers (ADR-0005). */
export function SkillPanel({ skills, hubResults, hubBusy, hubError, onSearch, onClear, onDetails, onImport, onRemove }: Props) {
  const [query, setQuery] = useState("");
  const builtinIds = skills.filter((s) => s.source.kind === "builtin").map((s) => s.id);

  return (
    <section className="panel">
      <h2>{t("panel.skills")}</h2>

      <form
        className="hub-search"
        onSubmit={(e) => {
          e.preventDefault();
          onSearch(query);
        }}
      >
        <input
          aria-label={t("hub.search")}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("hub.search.placeholder")}
          value={query}
        />
        <button className="btn" disabled={hubBusy} type="submit">
          {hubBusy ? t("hub.searching") : t("hub.search.button")}
        </button>
      </form>

      {hubResults !== null && (
        <div className="hub-results">
          <div className="hub-head">
            <span className="field-label">{t("hub.results", { count: hubResults.length })}</span>
            <button className="btn ghost" onClick={onClear} type="button">{t("hub.close")}</button>
          </div>
          {hubError && <div className="vlm">{t("hub.error")}</div>}
          {hubResults.length === 0 && !hubError && <div className="sub">{t("hub.none")}</div>}
          {hubResults.map((policy) => (
            <HubCard
              builtins={builtinIds}
              key={policy.repo}
              onDetails={onDetails}
              onImport={onImport}
              policy={policy}
            />
          ))}
        </div>
      )}

      {skills.map((s) => (
        <article className="card" key={s.id}>
          <div className="card-head">
            <span className="title">{text(s.name)}</span>
            <span className="tag">{t(s.intent ? "skill.kind.intent" : "skill.kind.behavior")}</span>
          </div>
          {s.summary && <div className="sub">{text(s.summary)}</div>}
          {s.source.kind === "hub" && (
            <div className="hub-origin">
              <a href={`https://huggingface.co/${s.source.repo}`} rel="noreferrer noopener" target="_blank">
                {s.source.repo}
              </a>
              <button
                className="danger-text"
                onClick={() => onRemove(s.id)}
                title={t("hub.remove")}
                type="button"
              >
                <Icon name="close" title={t("hub.remove")} />
              </button>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}

/**
 * A search result. Its details — what the repo says about its commands, whether anyone ran
 * it on hardware — are fetched at the moment someone moves to import it, so the decision is
 * made with those facts in front of them rather than after the fact.
 */
function HubCard({
  policy,
  builtins,
  onDetails,
  onImport,
}: {
  policy: HubPolicy;
  builtins: string[];
  onDetails: (repo: string) => Promise<HubPolicy | null>;
  onImport: (repo: string, slot: string) => void;
}) {
  const [details, setDetails] = useState<HubPolicy | null>(null);
  const [loading, setLoading] = useState(false);
  const shown = details ?? policy;
  const [slot, setSlot] = useState<string | null>(null);
  const chosen = slot ?? (shown.slot_guess && builtins.includes(shown.slot_guess) ? shown.slot_guess : (builtins[0] ?? "walk"));

  const open = async () => {
    setLoading(true);
    const fetched = await onDetails(policy.repo);
    setDetails(fetched ?? policy);
    setLoading(false);
  };

  return (
    <article className="card hub-card">
      <div className="card-head">
        <span className="title">{shown.name}</span>
        <span className="tag">{t("hub.downloads", { count: shown.downloads })}</span>
      </div>
      <div className="sub">{shown.author}</div>
      {shown.summary && <div className="sub">{shown.summary}</div>}
      <div className="chips">
        {shown.tags.slice(0, 4).map((tag) => <span className="chip" key={tag}>{tag}</span>)}
      </div>

      {details === null ? (
        <div className="actions">
          <button className="btn" disabled={loading} onClick={() => void open()} type="button">
            {loading ? t("hub.loading") : t("hub.import.start")}
          </button>
          <a className="btn ghost" href={shown.url} rel="noreferrer noopener" target="_blank">{t("hub.open")}</a>
        </div>
      ) : (
        <>
          {shown.hardware_tested === false && <div className="vlm">{t("hub.untested")}</div>}
          {shown.commands && <div className="sub commands">{t("hub.commands", { commands: shown.commands })}</div>}
          <label className="field">
            <span className="field-label">{t("hub.slot")}</span>
            <select onChange={(e) => setSlot(e.target.value)} value={chosen}>
              {builtins.map((id) => <option key={id} value={id}>{t(`skill.${id}`)}</option>)}
            </select>
          </label>
          <div className="sub">{t("hub.slot.hint")}</div>
          <div className="actions">
            <button className="btn primary" onClick={() => onImport(policy.repo, chosen)} type="button">
              <Icon name="plus" /> {t("hub.import")}
            </button>
            <button className="btn ghost" onClick={() => setDetails(null)} type="button">{t("hub.cancel")}</button>
          </div>
        </>
      )}
    </article>
  );
}

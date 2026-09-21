import { useState } from "react";

import { t, text } from "../i18n";
import type { HubPolicy, SkillManifest } from "../schemas";
import { Icon } from "../ui/Icon";

export interface HubProps {
  hubResults: HubPolicy[] | null;
  hubBusy: boolean;
  hubError: string | null;
  onSearch: (query: string) => void;
  onClear: () => void;
  onDetails: (repo: string) => Promise<HubPolicy | null>;
  onImport: (repo: string, slot: string) => void;
}

interface Props extends HubProps {
  skills: SkillManifest[];
  offline: boolean;
  onRemove: (id: string) => void;
}

/** The building blocks tab: what this Studio has, and what the Hub offers (ADR-0005).
 *  Blocks are not a permanent column any more; this page and the add-step picker are the
 *  two places they appear. */
export function Blocks({ skills, offline, onRemove, ...hub }: Props) {
  return (
    <div className="blocks">
      <p className="intro">{t("route.blocks.intro")}</p>
      <div className="blocks-grid">
        {offline && skills.length === 0 && <div className="sub">{t("offline.skills")}</div>}
        {skills.map((s) => (
          <article className="card block" key={s.id}>
            <div className="head">
              <div className="titles">
                <div className="title">{text(s.name)}</div>
                {s.summary && <div className="sub">{text(s.summary)}</div>}
              </div>
              <span className="tag">{t(s.intent ? "skill.kind.intent" : "skill.kind.behavior")}</span>
            </div>
            {s.source.kind === "hub" && (
              <div className="hub-origin">
                <a href={`https://huggingface.co/${s.source.repo}`} rel="noreferrer noopener" target="_blank">{s.source.repo}</a>
                <button className="iconbtn danger" onClick={() => onRemove(s.id)} title={t("hub.remove")} type="button">
                  <Icon name="close" title={t("hub.remove")} />
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
      <h3 className="section">{t("route.blocks.hub.title")}</h3>
      <HubSearch skills={skills} {...hub} />
    </div>
  );
}

/** Search the Hub and import a policy as a building block. Text from the Hub is data. */
export function HubSearch({ skills, hubResults, hubBusy, hubError, onSearch, onClear, onDetails, onImport }: HubProps & { skills: SkillManifest[] }) {
  const [query, setQuery] = useState("");
  const builtinIds = skills.filter((s) => s.source.kind === "builtin").map((s) => s.id);
  return (
    <div className="hub">
      <form
        className="hub-search"
        onSubmit={(e) => {
          e.preventDefault();
          onSearch(query);
        }}
      >
        <input aria-label={t("hub.search")} onChange={(e) => setQuery(e.target.value)} placeholder={t("hub.search.placeholder")} value={query} />
        <button className="btn" disabled={hubBusy} type="submit">{hubBusy ? t("hub.searching") : t("hub.search.button")}</button>
      </form>
      {hubResults !== null && (
        <div className="hub-results">
          <div className="hub-head">
            <span className="label">{t("hub.results", { count: hubResults.length })}</span>
            <button className="btn quiet small" onClick={onClear} type="button">{t("hub.close")}</button>
          </div>
          {hubError && <div className="vlm">{t("hub.error")}</div>}
          {hubResults.length === 0 && !hubError && <div className="sub">{t("hub.none")}</div>}
          {hubResults.map((policy) => (
            <HubCard builtins={builtinIds} key={policy.repo} onDetails={onDetails} onImport={onImport} policy={policy} />
          ))}
        </div>
      )}
    </div>
  );
}

function HubCard({ policy, builtins, onDetails, onImport }: { policy: HubPolicy; builtins: string[]; onDetails: (repo: string) => Promise<HubPolicy | null>; onImport: (repo: string, slot: string) => void }) {
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
      <div className="head">
        <div className="titles">
          <div className="title">{shown.name}</div>
          <div className="sub">{shown.author}{shown.summary ? ` — ${shown.summary}` : ""}</div>
        </div>
        <span className="tag">{t("hub.downloads", { count: shown.downloads })}</span>
      </div>
      {shown.tags.length > 0 && <div className="facts">{shown.tags.slice(0, 4).map((tag) => <span className="k" key={tag}>{tag}</span>)}</div>}
      {details === null ? (
        <div className="row">
          <button className="btn small" disabled={loading} onClick={() => void open()} type="button">{loading ? t("hub.loading") : t("hub.import.start")}</button>
          <a className="btn small quiet" href={shown.url} rel="noreferrer noopener" target="_blank">{t("hub.open")}</a>
        </div>
      ) : (
        <>
          {shown.hardware_tested === false && <div className="vlm">{t("hub.untested")}</div>}
          {shown.commands && <div className="sub commands">{t("hub.commands", { commands: shown.commands })}</div>}
          <label className="field">
            <span>{t("hub.slot")}</span>
            <select onChange={(e) => setSlot(e.target.value)} value={chosen}>
              {builtins.map((id) => <option key={id} value={id}>{t(`skill.${id}`)}</option>)}
            </select>
          </label>
          <div className="sub">{t("hub.slot.hint")}</div>
          <div className="row">
            <button className="btn primary small" onClick={() => onImport(policy.repo, chosen)} type="button"><Icon name="plus" /> {t("hub.import")}</button>
            <button className="btn quiet small" onClick={() => setDetails(null)} type="button">{t("hub.cancel")}</button>
          </div>
        </>
      )}
    </article>
  );
}

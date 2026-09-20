import { t } from "../i18n";
import type { SkillManifest } from "../schemas";

export function SkillPanel({ skills }: { skills: SkillManifest[] }) {
  return (
    <section className="panel">
      <h2>{t("panel.skills")}</h2>
      {skills.map((s) => (
        <article className="card" key={s.id}>
          <div className="card-head">
            <span className="title">{s.name.de}</span>
            <span className="tag">{t(s.intent ? "skill.kind.intent" : "skill.kind.behavior")}</span>
          </div>
          {s.summary && <div className="sub">{s.summary.de}</div>}
        </article>
      ))}
    </section>
  );
}

import { t, text } from "../i18n";
import type { SkillManifest } from "../schemas";

export function SkillPanel({ skills }: { skills: SkillManifest[] }) {
  return (
    <section className="panel">
      <h2>{t("panel.skills")}</h2>
      {skills.map((s) => (
        <article className="card" key={s.id}>
          <div className="card-head">
            <span className="title">{text(s.name)}</span>
            <span className="tag">{t(s.intent ? "skill.kind.intent" : "skill.kind.behavior")}</span>
          </div>
          {s.summary && <div className="sub">{text(s.summary)}</div>}
        </article>
      ))}
    </section>
  );
}

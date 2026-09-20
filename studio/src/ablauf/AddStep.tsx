import { useState } from "react";

import { t } from "../i18n";
import type { SkillManifest, Step } from "../schemas";
import { newPerceiveStep, newSkillStep, newWaitStep } from "../editor/model";
import { skillGroups } from "./Controls";

/** The last station while editing: opens the building-block picker (§3.1: blocks appear
 *  when you need them, they are not a permanent column). */
export function AddStep({ skills, onAdd }: { skills: SkillManifest[]; onAdd: (step: Step) => void }) {
  const [open, setOpen] = useState(false);
  const groups = skillGroups(skills);
  const add = (step: Step) => {
    onAdd(step);
    setOpen(false);
  };
  return (
    <div className="station add">
      <div className="node">+</div>
      <div className="card">
        {!open ? (
          <button className="btn quiet" onClick={() => setOpen(true)} type="button">+ {t("steps.add")}</button>
        ) : (
          <div className="picker">
            <div className="head">
              <div className="titles"><div className="title">{t("steps.add")}</div></div>
              <div className="actions">
                <button className="iconbtn" onClick={() => setOpen(false)} title={t("steps.add.close")} type="button">✕</button>
              </div>
            </div>
            <div className="groups">
              <div>
                <h3>{t("steps.group.perceive")}</h3>
                <button className="option" onClick={() => add(newPerceiveStep())} type="button">
                  <div className="name">{t("steps.perceive.person")}</div>
                  <div className="desc">{t("steps.perceive.person.summary")}</div>
                </button>
              </div>
              <div>
                <h3>{t("steps.group.move")}</h3>
                {groups.move.map((s) => <SkillOption key={s.id} onPick={() => add(newSkillStep(s))} skill={s} />)}
              </div>
              <div>
                <h3>{t("steps.group.behavior")}</h3>
                {groups.behavior.map((s) => <SkillOption key={s.id} onPick={() => add(newSkillStep(s))} skill={s} />)}
              </div>
              <div>
                <h3>{t("steps.group.wait")}</h3>
                <button className="option" onClick={() => add(newWaitStep())} type="button">
                  <div className="name">{t("steps.group.wait")}</div>
                  <div className="desc">{t("steps.wait.summary")}</div>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SkillOption({ skill, onPick }: { skill: SkillManifest; onPick: () => void }) {
  return (
    <button className="option" onClick={onPick} type="button">
      <div className="name">{skill.name.de}</div>
      {skill.summary && <div className="desc">{skill.summary.de}</div>}
    </button>
  );
}

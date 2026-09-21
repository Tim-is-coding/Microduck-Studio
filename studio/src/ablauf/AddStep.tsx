import { t, text } from "../i18n";
import type { SkillManifest, Step } from "../schemas";
import { newPerceiveStep, newSkillStep, newWaitStep, setPerceiveQuery } from "../editor/model";
import { HubSearch, type HubProps } from "../skills/Blocks";
import { Icon } from "../ui/Icon";
import { skillGroups } from "./Controls";

interface Props extends HubProps {
  skills: SkillManifest[];
  onAdd: (step: Step) => void;
  onClose: () => void;
}

/** The building-block picker: opens in a gap of the route (§3.1: blocks appear when you
 *  need them). The Hub is one fold further down for the case that a block is missing. */
export function AddStepPicker({ skills, onAdd, onClose, ...hub }: Props) {
  const groups = skillGroups(skills);
  return (
    <div className="picker">
      <div className="head">
        <div className="titles"><div className="title">{t("route.add")}</div></div>
        <div className="actions">
          <button className="iconbtn" onClick={onClose} title={t("route.add.close")} type="button"><Icon name="close" title={t("route.add.close")} /></button>
        </div>
      </div>
      <div className="groups">
        <div>
          <h3>{t("route.group.perceive")}</h3>
          <button className="option" onClick={() => onAdd(newPerceiveStep())} type="button">
            <div className="name">{t("route.perceive.person")}</div>
            <div className="desc">{t("route.perceive.person.summary")}</div>
          </button>
          <button className="option" onClick={() => onAdd(setPerceiveQuery(newPerceiveStep(), "vlm.target"))} type="button">
            <div className="name">{t("route.perceive.vlm")}</div>
            <div className="desc">{t("route.perceive.vlm.summary")}</div>
          </button>
        </div>
        <div>
          <h3>{t("route.group.move")}</h3>
          {groups.move.map((s) => <SkillOption key={s.id} onPick={() => onAdd(newSkillStep(s))} skill={s} />)}
        </div>
        <div>
          <h3>{t("route.group.behavior")}</h3>
          {groups.behavior.map((s) => <SkillOption key={s.id} onPick={() => onAdd(newSkillStep(s))} skill={s} />)}
        </div>
        <div>
          <h3>{t("route.group.wait")}</h3>
          <button className="option" onClick={() => onAdd(newWaitStep())} type="button">
            <div className="name">{t("route.group.wait")}</div>
            <div className="desc">{t("route.wait.summary")}</div>
          </button>
        </div>
      </div>
      <details className="more">
        <summary>{t("route.blocks.from_hub")}</summary>
        <HubSearch skills={skills} {...hub} />
      </details>
    </div>
  );
}

function SkillOption({ skill, onPick }: { skill: SkillManifest; onPick: () => void }) {
  return (
    <button className="option" onClick={onPick} type="button">
      <div className="name">{text(skill.name)}</div>
      {skill.summary && <div className="desc">{text(skill.summary)}</div>}
    </button>
  );
}

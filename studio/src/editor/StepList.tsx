import { formatDuration, phrases as phraseList, quoteJoin, t, text, tOr } from "../i18n";
import {
  isPerceive,
  isSkill,
  isWait,
  parseCondition,
  type BehaviorPackFromApi,
  type SkillManifest,
  type SkillStep,
  type StopCondition,
  type Trigger,
} from "../schemas";

interface Props {
  behavior: BehaviorPackFromApi;
  skills: Map<string, SkillManifest>;
  activeStep?: number | null;
  interrupt?: string | null;
}

/** Read-only rendering of a behavior pack as a vertical step list with side branches (§3.2). */
export function StepList({ behavior, skills, activeStep = null, interrupt = null }: Props) {
  return (
    <div>
      {behavior.problems.length > 0 && (
        <div className="card problems">
          <div className="title">{t("editor.problems")}</div>
          <ul>{behavior.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}
      {behavior.vlm && <div className="vlm">{t("editor.vlm", { provider: behavior.vlm.provider })}</div>}

      <div className="step">
        <div className="num trigger">▶</div>
        <div className="card"><div className="title">{describeTrigger(behavior.trigger)}</div></div>
      </div>

      {behavior.steps.map((step, i) => (
        <div className={`step${activeStep === i && !interrupt ? " active" : ""}`} key={i}>
          <div className="num">{i + 1}</div>
          <div className="card">
            {isPerceive(step) && (
              <>
                <div className="title">
                  {step.question
                    ? t("editor.step.ask", { question: text(step.question) })
                    : t("editor.step.perceive", { what: tOr(`perceive.${step.perceive}`, step.perceive) })}
                </div>
                {step.on_none && (
                  <div className="branch">
                    {t("editor.step.on_none", {
                      do: text(skills.get(step.on_none.do)?.name, step.on_none.do),
                      seconds: step.on_none.seconds,
                      then: t(`then.${step.on_none.then}`),
                    })}
                  </div>
                )}
              </>
            )}
            {isSkill(step) && <SkillCard step={step} skill={skills.get(step.skill)} />}
            {isWait(step) && <div className="title">{t("editor.step.wait", { duration: formatDuration(step.wait) })}</div>}
          </div>
        </div>
      ))}

      {behavior.always.map((rule, i) => (
        <div className={`step${interrupt === rule.on ? " active" : ""}`} key={`always-${i}`}>
          <div className="num always">!</div>
          <div className="card">
            <div className="title">
              {t("editor.always", {
                on: describeSignal(rule.on),
                do: rule.do.map((a) => text(skills.get(a)?.name, tOr(`action.${a}`, a))).join(", "),
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SkillCard({ step, skill }: { step: SkillStep; skill: SkillManifest | undefined }) {
  if (!skill) return <div className="title problems">{t("editor.step.unknown_skill", { id: step.skill })}</div>;
  return (
    <>
      <div className="title">{text(skill.name)}</div>
      {skill.summary && <div className="sub">{text(skill.summary)}</div>}
      <div className="chips">
        {Object.entries(step.with).map(([key, value]) => {
          const control = skill.ui[key];
          const unit = control && "unit" in control && control.unit ? ` ${control.unit}` : "";
          const label = typeof value === "string" ? tOr(`opt.${value}`, value) : `${value}${unit}`;
          return (
            <span className="chip" key={key}>
              {tOr(`ui.${key}`, key)}: <b>{label}</b>
            </span>
          );
        })}
      </div>
      {step.until && (
        <div className="branch until">
          {t("editor.step.until", {
            conditions: (step.until.any ?? step.until.all ?? [])
              .map(describeStopCondition)
              .join(step.until.any ? t("cond.or") : t("cond.and")),
          })}
        </div>
      )}
    </>
  );
}

function describeTrigger(trigger: Trigger): string {
  if (trigger.kind === "speech")
    return t("editor.trigger.speech", { phrases: quoteJoin(phraseList(trigger.phrases), ", ") });
  return t("editor.trigger.manual");
}

function describeStopCondition(c: StopCondition): string {
  if ("speech" in c) return t("cond.speech", { phrases: quoteJoin(phraseList(c.speech)) });
  if ("elapsed" in c) return t("cond.elapsed", { duration: formatDuration(c.elapsed) });
  return describeSignal(c.signal);
}

function describeSignal(text: string): string {
  const cond = parseCondition(text);
  const name = tOr(`signal.${cond.signal}`, cond.signal);
  return cond.op ? `${name} ${cond.op} ${cond.value}` : name;
}

import { t, tOr } from "../i18n";
import type { Event, ExecutorStatus, RobotState, RuntimeHealth } from "../schemas";
import { CameraView } from "./CameraView";
import { TofGrid } from "./TofGrid";
import { degrees, formatDistance } from "./overlay";

interface Props {
  health: RuntimeHealth | null;
  state: RobotState | null;
  executor: ExecutorStatus | null;
  events: Event[];
  onStop: () => void;
}

export function LivePanel({ health, state, executor, events, onStop }: Props) {
  const connected = health?.connected ?? false;
  const running = executor?.state === "running";

  return (
    <section className="panel live">
      <h2>{t("panel.live")}</h2>

      <div className={`doing${running ? " running" : ""}`}>
        <div className="doing-line">{headline(executor)}</div>
        {running && executor && executor.step_count > 0 && (
          <div className="progress" aria-hidden="true">
            {Array.from({ length: executor.step_count }, (_, i) => (
              <span className={stepClass(i, executor)} key={i} />
            ))}
          </div>
        )}
      </div>

      <CameraView connected={connected} executor={executor} />

      <div className="chips">
        {state ? (
          <>
            {describeFlags(state).map((label) => (
              <span className="chip" key={label}>{label}</span>
            ))}
            {state.pose && (
              <span className="chip">
                {t("live.pose")}: <b>{state.pose.x.toFixed(2)} / {state.pose.y.toFixed(2)} m</b>
              </span>
            )}
          </>
        ) : (
          <span className="chip">{t("live.state.none")}</span>
        )}
        {connected && <span className="chip person">{describePerson(executor)}</span>}
        {executor?.target && <span className="chip target">{describeTarget(executor)}</span>}
      </div>

      {executor?.vlm?.question && (
        <div className={executor.vlm.sends_frames ? "vlm" : "sub vlm-line"}>
          {executor.vlm.sends_frames
            ? t("live.vlm.sending", { provider: tOr(`vlm.provider.${executor.vlm.provider}`, executor.vlm.provider), question: executor.vlm.question })
            : t("live.vlm.local", { question: executor.vlm.question })}
          {executor.vlm.answer && ` · ${executor.vlm.answer.answer}`}
          {` · ${t("live.vlm.asked", { count: executor.vlm.asked })}`}
        </div>
      )}

      <TofGrid minM={executor?.tof_min_m} rows={executor?.tof_rows} />

      <div className="meta">
        <span>{t("live.backend")}: {health?.backend ?? "–"}</span>
        <span>{t("live.battery")}: {health?.health ? `${Math.round(health.health.battery * 100)} %` : "–"}</span>
        {health?.vlm && (
          <span title={health.vlm.model}>
            {t("live.vlm")}: {health.vlm.configured
              ? tOr(`vlm.provider.${health.vlm.provider}`, health.vlm.provider)
              : t("live.vlm.off", { provider: health.vlm.provider })}
          </span>
        )}
      </div>

      <button className="stop" onClick={onStop} type="button">■ {t("live.stop")}</button>

      <h2>{t("live.log")}</h2>
      {events.length === 0 ? (
        <div className="sub">{t("live.log.empty")}</div>
      ) : (
        <ul className="log">
          {[...events].reverse().slice(0, 50).map((e, i) => (
            <li className={e.level} key={`${e.ts}-${i}`}>
              <time>{new Date(e.ts * 1000).toLocaleTimeString("de-DE")}</time>
              {e.text.de}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** One sentence: what is the duck doing right now? */
function headline(executor: ExecutorStatus | null): string {
  if (!executor || executor.state === "idle") return t("live.doing.idle");
  if (executor.state === "running") {
    const step = t("live.doing.step", { step: (executor.step_index ?? 0) + 1, count: executor.step_count });
    if (executor.interrupt) return `${step} · ${t("live.doing.interrupt", { on: tOr(`signal.${executor.interrupt}`, executor.interrupt) })}`;
    const skill = executor.active_skill ? ` · ${tOr(`skill.${executor.active_skill}`, executor.active_skill)}` : "";
    return `${step}${skill}`;
  }
  const label = t(`run.state.${executor.state}`);
  return executor.reason ? `${label}: ${executor.reason}` : label;
}

function stepClass(index: number, executor: ExecutorStatus): string {
  const active = executor.step_index ?? -1;
  if (index < active) return "done";
  return index === active ? "now" : "todo";
}

function describeFlags(state: RobotState): string[] {
  const out: string[] = [];
  if (state.flags.fallen) out.push(t("state.fallen"));
  else if (state.flags.sitting) out.push(t("state.sitting"));
  else if (state.flags.standing) out.push(t("state.standing"));
  out.push(t(state.flags.moving ? "state.moving" : "state.idle"));
  return out;
}

function describeTarget(executor: ExecutorStatus | null): string {
  const target = executor?.target;
  if (!target) return t("live.target.none");
  const distance = target.distance_m != null ? `${formatDistance(target.distance_m)} · ` : "";
  return t("live.target.at", {
    label: target.label,
    distance,
    degrees: degrees(target.bearing_rad),
    side: t(target.bearing_rad >= 0 ? "live.person.left" : "live.person.right"),
  });
}

function describePerson(executor: ExecutorStatus | null): string {
  const p = executor?.person;
  if (!p) return t("live.person.none");
  const distance = p.distance_m != null ? `${formatDistance(p.distance_m)} · ` : "";
  return t("live.person.at", {
    distance,
    degrees: degrees(p.bearing_rad),
    side: t(p.bearing_rad >= 0 ? "live.person.left" : "live.person.right"),
  });
}

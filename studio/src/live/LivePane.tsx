import { formatTime, number, t, text, tOr } from "../i18n";
import type { Event, ExecutorStatus, RobotState, RunRecord, RuntimeHealth } from "../schemas";
import { Icon } from "../ui/Icon";
import { CameraView } from "./CameraView";
import { TofGrid } from "./TofGrid";
import { degrees, formatDuration } from "./overlay";

interface Props {
  health: RuntimeHealth | null;
  offline: boolean;
  state: RobotState | null;
  executor: ExecutorStatus | null;
  /** The last few runs, newest first — the stage keeps the five most recent in view. */
  runs: RunRecord[];
  events: Event[];
  onStop: () => void;
}

/** The stage: what the duck sees and does, and the one button that always works. */
export function LivePane({ health, offline, state, executor, runs, events, onStop }: Props) {
  const connected = health?.connected ?? false;
  return (
    <aside className="live">
      <h2>{t("stage.title")}</h2>
      <CameraView connected={connected} executor={executor} />
      <p className="sentence">
        {stateSentence(offline, connected, state)} <span className="soft">{connected ? sightingSentence(executor) : ""}</span>
      </p>
      {executor?.vlm?.question && (
        <p className={`vlmline${executor.vlm.sends_frames ? " sending" : ""}`}>
          {executor.vlm.sends_frames
            ? t("live.vlm.sending", { provider: tOr(`vlm.provider.${executor.vlm.provider}`, executor.vlm.provider), question: text(executor.vlm.question) })
            : t("live.vlm.local", { question: text(executor.vlm.question) })}
          {executor.vlm.answer?.answer ? ` ${executor.vlm.answer.answer}` : ""}
        </p>
      )}
      <TofGrid minM={executor?.tof_min_m} rows={executor?.tof_rows} />
      <button className="estop" onClick={onStop} type="button"><Icon name="stop" /> {t("live.stop")}</button>
      <div className="logwrap">
        <h2>{t("stage.log")}</h2>
        {events.length === 0 ? (
          <p className="meta">{t("live.log.empty")}</p>
        ) : (
          <ul className="log">
            {[...events].reverse().slice(0, 60).map((e, i) => (
              <li className={e.level} key={`${e.ts}-${i}`}>
                <time>{formatTime(e.ts * 1000).replace(/:\d\d(\s|$)/, "$1")}</time>
                <span>{text(e.text)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="runswrap">
        <h2>{t("live.runs")}</h2>
        {runs.length === 0 ? (
          <p className="meta">{t("live.runs.none")}</p>
        ) : (
          <ul className="runs">
            {runs.slice(0, 5).map((run, i) => (
              <li key={`${run.started_at}-${i}`}>
                <time>{formatTime(run.started_at * 1000).replace(/:\d\d(\s|$)/, "$1")}</time>
                <span className="what">{text(run.name)}</span>
                <span className={`outcome ${run.state}`}>{t(`run.state.${run.state}`)}</span>
                <span className="detail">
                  {formatDuration(run.duration_s)} · {t("live.runs.steps", { done: run.steps_done, count: run.step_count })}
                  {run.reason ? ` · ${text(run.reason)}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {health && (
        <p className="meta">
          {t(`stage.backend.${health.backend}`)}
          {health.health ? `, ${t("stage.battery", { percent: Math.round(health.health.battery * 100) })}` : ""}
          {health.vlm ? `, ${t("live.vlm")}: ${health.vlm.configured ? tOr(`vlm.provider.${health.vlm.provider}`, health.vlm.provider) : t("live.vlm.off", { provider: health.vlm.provider })}` : ""}
        </p>
      )}
    </aside>
  );
}

function stateSentence(offline: boolean, connected: boolean, state: RobotState | null): string {
  if (offline) return t("live.doing.offline");
  if (!connected) return t("stage.state.disconnected");
  if (!state) return t("stage.state.unknown");
  if (state.flags.fallen) return t("stage.state.fallen");
  if (state.flags.sitting) return t("stage.state.sitting");
  if (state.flags.moving) return t("stage.state.moving");
  return t("stage.state.standing");
}

function sightingSentence(executor: ExecutorStatus | null): string {
  const target = executor?.target;
  if (target) {
    const distance = target.distance_m != null ? `${number(target.distance_m, 1)} m ` : "";
    return t("stage.target.at", { label: text(target.label), distance, degrees: degrees(target.bearing_rad), side: t(target.bearing_rad >= 0 ? "stage.left" : "stage.right") });
  }
  const p = executor?.person;
  if (!p) return t("stage.person.none");
  const deg = Math.abs((p.bearing_rad * 180) / Math.PI);
  const distance = p.distance_m != null ? `${number(p.distance_m, 1)} m ` : "";
  if (deg < 3) return t("stage.person.ahead", { distance });
  return t("stage.person.at", { distance, degrees: deg.toFixed(0), side: t(p.bearing_rad >= 0 ? "stage.left" : "stage.right") });
}

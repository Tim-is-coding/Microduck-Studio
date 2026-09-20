import { useEffect, useState } from "react";

import { t } from "../i18n";
import type { Event, ExecutorStatus, RobotState, RuntimeHealth } from "../schemas";

interface Props {
  health: RuntimeHealth | null;
  state: RobotState | null;
  executor: ExecutorStatus | null;
  events: Event[];
  onStop: () => void;
}

const FRAME_INTERVAL_MS = 500; // 2 fps (CLAUDE.md §5)

/** The stage: what the duck sees and does, and the one button that always works. */
export function LivePane({ health, state, executor, events, onStop }: Props) {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [noCamera, setNoCamera] = useState(false);
  const connected = health?.connected ?? false;

  useEffect(() => {
    if (!connected) {
      setFrameUrl(null);
      setNoCamera(false);
      return;
    }
    const tick = () => setFrameUrl(`/api/frame?t=${Date.now()}`);
    tick();
    const id = setInterval(tick, FRAME_INTERVAL_MS);
    return () => clearInterval(id);
  }, [connected]);

  return (
    <aside className="live">
      <h2>{t("live.title")}</h2>
      <div className="camera">
        {frameUrl && !noCamera ? (
          <img alt="" onError={() => setNoCamera(true)} onLoad={() => setNoCamera(false)} src={frameUrl} />
        ) : (
          <span>{t(connected ? "live.camera.none" : "live.camera.offline")}</span>
        )}
      </div>
      <p className="sentence">
        {stateSentence(connected, state)} <span className="soft">{connected ? personSentence(executor) : ""}</span>
      </p>
      <button className="estop" onClick={onStop} type="button">■ {t("live.stop")}</button>
      <div className="logwrap">
        {events.length === 0 ? (
          <p className="meta">{t("live.log.empty")}</p>
        ) : (
          <ul className="log">
            {[...events].reverse().slice(0, 60).map((e, i) => (
              <li className={e.level} key={`${e.ts}-${i}`}>
                <time>{new Date(e.ts * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}</time>
                <span>{e.text.de}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {health && (
        <p className="meta">
          {t(`live.backend.${health.backend}`)}
          {health.health ? `, ${t("live.battery", { percent: Math.round(health.health.battery * 100) })}` : ""}
        </p>
      )}
    </aside>
  );
}

function stateSentence(connected: boolean, state: RobotState | null): string {
  if (!connected) return t("live.state.disconnected");
  if (!state) return t("live.state.unknown");
  if (state.flags.fallen) return t("live.state.fallen");
  if (state.flags.sitting) return t("live.state.sitting");
  if (state.flags.moving) return t("live.state.moving");
  return t("live.state.standing");
}

function personSentence(executor: ExecutorStatus | null): string {
  const p = executor?.person;
  if (!p) return t("live.person.none");
  const degrees = Math.abs((p.bearing_rad * 180) / Math.PI);
  const distance = p.distance_m != null ? `${p.distance_m.toLocaleString("de-DE", { maximumFractionDigits: 1 })} m ` : "";
  if (degrees < 3) return t("live.person.ahead", { distance });
  return t("live.person.at", { distance, degrees: degrees.toFixed(0), side: t(p.bearing_rad >= 0 ? "live.person.left" : "live.person.right") });
}

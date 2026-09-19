import { useEffect, useState } from "react";

import { t } from "../i18n";
import type { Event, RobotState, RuntimeHealth } from "../schemas";

interface Props {
  health: RuntimeHealth | null;
  state: RobotState | null;
  events: Event[];
  onStop: () => void;
}

const FRAME_INTERVAL_MS = 500; // 2 fps, CLAUDE.md §5 "Kamera (2 fps JPEG)"

export function LivePanel({ health, state, events, onStop }: Props) {
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
    <section className="panel live">
      <h2>{t("panel.live")}</h2>
      <div className="camera">
        {frameUrl && !noCamera ? (
          <img src={frameUrl} alt={t("live.camera")} onError={() => setNoCamera(true)} onLoad={() => setNoCamera(false)} />
        ) : (
          <span>{t(noCamera ? "live.camera.none" : "live.camera.offline")}</span>
        )}
      </div>
      <div className="chips">
        {state ? (
          <>
            {describeFlags(state).map((label) => <span className="chip" key={label}>{label}</span>)}
            {state.pose && (
              <span className="chip">
                {t("live.pose")}: <b>{state.pose.x.toFixed(2)} / {state.pose.y.toFixed(2)} m</b>
              </span>
            )}
          </>
        ) : (
          <span className="chip">{t("live.state.none")}</span>
        )}
      </div>
      <div className="meta">
        <span>{t("live.backend")}: {health?.backend ?? "–"}</span>
        <span>{t("live.battery")}: {health?.health ? `${Math.round(health.health.battery * 100)} %` : "–"}</span>
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

function describeFlags(state: RobotState): string[] {
  const out: string[] = [];
  if (state.flags.fallen) out.push(t("state.fallen"));
  else if (state.flags.sitting) out.push(t("state.sitting"));
  else if (state.flags.standing) out.push(t("state.standing"));
  out.push(t(state.flags.moving ? "state.moving" : "state.idle"));
  return out;
}

import { useEffect, useState, type CSSProperties } from "react";

import { t } from "../i18n";
import type { ExecutorStatus } from "../schemas";
import { layoutMarkers, marker, tagBox, type Marker } from "./overlay";

const FRAME_INTERVAL_MS = 500; // 2 fps, CLAUDE.md §5 "Kamera (2 fps JPEG)"

interface Props {
  connected: boolean;
  executor: ExecutorStatus | null;
}

/**
 * The camera picture with what perception saw drawn on top: the person the local detector
 * tracks, and the thing a VLM was asked to find (ADR-0004).
 *
 * The overlay uses the frame's own pixel coordinates as its viewBox and the same fit rule as
 * the picture (`object-fit: contain` ↔ `preserveAspectRatio="xMidYMid meet"`), so a marker
 * sits on the thing at any size — the duck's frames are portrait (360x640), the mock's are
 * a small 64x48.
 */
export function CameraView({ connected, executor }: Props) {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [noCamera, setNoCamera] = useState(false);
  const [ratio, setRatio] = useState<string | null>(null); // the frame's own aspect ratio

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

  const sighting = executor?.target ?? executor?.person ?? null;
  const markers = layoutMarkers(
    [
      marker(executor?.person, "person", t("live.person")),
      marker(executor?.target, "target", executor?.target?.label ?? t("live.target")),
    ].filter((m): m is Marker => m !== null),
  );

  const showPicture = Boolean(frameUrl) && !noCamera;
  return (
    <div className="camera" style={ratio ? ({ "--camera-ratio": ratio } as CSSProperties) : undefined}>
      {showPicture ? (
        <img
          alt={t("live.camera")}
          onError={() => setNoCamera(true)}
          onLoad={(e) => {
            const img = e.currentTarget;
            if (img.naturalWidth && img.naturalHeight) setRatio(`${img.naturalWidth} / ${img.naturalHeight}`);
            setNoCamera(false);
          }}
          src={frameUrl!}
        />
      ) : (
        <span>{t(noCamera ? "live.camera.none" : "live.camera.offline")}</span>
      )}
      {showPicture && sighting && markers.length > 0 && (
        <svg
          className="overlay"
          preserveAspectRatio="xMidYMid meet"
          viewBox={`0 0 ${sighting.frame_width} ${sighting.frame_height}`}
        >
          <line className="axis" x1={sighting.frame_width / 2} x2={sighting.frame_width / 2} y1={0} y2={sighting.frame_height} />
          {markers.map((m) => (
            <Crosshair frameHeight={sighting.frame_height} frameWidth={sighting.frame_width} key={m.kind} marker={m} />
          ))}
        </svg>
      )}
    </div>
  );
}

function Crosshair({ marker: m, frameWidth, frameHeight }: { marker: Marker; frameWidth: number; frameHeight: number }) {
  const u = Math.min(frameWidth, frameHeight) / 100; // one "percent" of the short edge
  const x = m.x * frameWidth;
  const y = m.y * frameHeight;
  const fontSize = 6 * u;
  const tag = tagBox(x, m.label, fontSize, 10 * u, frameWidth);
  const tagY = y - m.labelDy * u - fontSize * 1.4;
  return (
    <g className={`mark ${m.kind}`} style={{ strokeWidth: 0.9 * u }}>
      <circle className="halo" cx={x} cy={y} r={7 * u} />
      <circle className="dot" cx={x} cy={y} r={1.8 * u} />
      <line x1={x - 12 * u} x2={x - 3 * u} y1={y} y2={y} />
      <line x1={x + 3 * u} x2={x + 12 * u} y1={y} y2={y} />
      <line x1={x} x2={x} y1={y - 12 * u} y2={y - 3 * u} />
      <line x1={x} x2={x} y1={y + 3 * u} y2={y + 12 * u} />
      <rect className="tag" height={fontSize * 1.5} rx={fontSize * 0.35} width={tag.width} x={tag.x} y={tagY} />
      <text className="label" style={{ fontSize }} x={tag.x + fontSize * 0.5} y={tagY + fontSize * 1.1}>
        {m.label}
      </text>
    </g>
  );
}

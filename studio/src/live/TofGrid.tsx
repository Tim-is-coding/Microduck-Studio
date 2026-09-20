import { t } from "../i18n";
import { TOF_RANGE_M, closestZone, formatDistance, zoneColor } from "./overlay";

/**
 * The 8x8 depth sensor in the head, as 64 squares: warm where something is close, pale where
 * the way is clear. The closest zone straight ahead gets a ring — that is the one that ends
 * a walk step (`tof_distance < 0.25`).
 */
export function TofGrid({ rows, minM }: { rows?: number[][] | null; minM?: number | null }) {
  if (!rows || rows.length === 0) return null;
  const closest = closestZone(rows);
  return (
    <div className="tof">
      <div className="tof-grid" role="img" aria-label={t("live.tof.alt")}>
        {rows.map((row, r) =>
          row.map((distanceM, c) => (
            <span
              className={`zone${closest && closest.row === r && closest.col === c ? " closest" : ""}`}
              key={`${r}-${c}`}
              style={{ background: zoneColor(distanceM) }}
              title={distanceM >= TOF_RANGE_M ? t("live.tof.empty") : formatDistance(distanceM)}
            />
          )),
        )}
      </div>
      <div className="tof-legend">
        <span className="field-label">{t("live.tof")}</span>
        <span>{minM != null ? t("live.tof.nearest", { distance: formatDistance(minM) }) : t("live.tof.clear")}</span>
      </div>
    </div>
  );
}

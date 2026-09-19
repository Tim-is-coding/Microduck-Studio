import { tOr } from "../i18n";
import type { UiControl as UiControlSpec } from "../schemas";

type Scalar = string | number | boolean;

interface Props {
  name: string;
  spec: UiControlSpec;
  value: Scalar | undefined;
  onChange: (value: Scalar) => void;
}

/** One card control, rendered from a manifest `ui` entry (§6.1): the non-technical view. */
export function UiControl({ name, spec, value, onChange }: Props) {
  const label = tOr(`ui.${name}`, name);
  switch (spec.control) {
    case "choice":
      return (
        <div className="field">
          <span className="field-label">{label}</span>
          <div className="seg">
            {spec.options.map((opt) => (
              <button
                className={value === opt || (value === undefined && spec.default === opt) ? "active" : ""}
                key={opt}
                onClick={() => onChange(opt)}
                type="button"
              >
                {tOr(`opt.${opt}`, opt)}
              </button>
            ))}
          </div>
        </div>
      );
    case "select":
      return (
        <label className="field">
          <span className="field-label">{label}</span>
          <select onChange={(e) => onChange(e.target.value)} value={String(value ?? spec.default ?? spec.options[0])}>
            {spec.options.map((opt) => (
              <option key={opt} value={opt}>{tOr(`opt.${opt}`, opt)}</option>
            ))}
          </select>
        </label>
      );
    case "range": {
      const v = typeof value === "number" ? value : (spec.default ?? spec.min);
      return (
        <label className="field">
          <span className="field-label">
            {label}: <b>{v}{spec.unit ? ` ${spec.unit}` : ""}</b>
          </span>
          <input
            max={spec.max}
            min={spec.min}
            onChange={(e) => onChange(Number(e.target.value))}
            step={spec.step ?? 1}
            type="range"
            value={v}
          />
        </label>
      );
    }
    case "toggle":
      return (
        <label className="field inline">
          <input checked={Boolean(value ?? spec.default)} onChange={(e) => onChange(e.target.checked)} type="checkbox" />
          <span className="field-label">{label}</span>
        </label>
      );
  }
}

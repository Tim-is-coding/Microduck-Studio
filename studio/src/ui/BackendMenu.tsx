import { useEffect, useRef, useState } from "react";

import { t } from "../i18n";
import type { BackendKind, RuntimeHealth } from "../schemas";
import { useStudio } from "../store/useStudio";
import { Icon } from "./Icon";

type RuntimeStatus = "loading" | "online" | "offline";

/** The order a person meets them in: the normal state first (§3.3), the real duck last. */
const ORDER: BackendKind[] = ["sim", "mock", "duck"];
const HOST_PLACEHOLDER = "duck.local";

/**
 * Which duck the Studio works with (ADR-0007). The status in the top bar is the button: it
 * says what is connected, and opening it says what else there is and what each one needs.
 * The real duck needs a tunnel a person opens in a terminal (ADR-0006) — the Studio shows
 * the exact command, it never runs it.
 */
export function BackendMenu({ runtime, health }: { runtime: RuntimeStatus; health: RuntimeHealth | null }) {
  const switchBackend = useStudio((s) => s.switchBackend);
  const running = useStudio((s) => s.executor?.state === "running");
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<BackendKind | null>(null);
  const [host, setHost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  const current = health?.backend ?? null;
  const shown = pending ?? current;

  useEffect(() => {
    if (!open) return;
    setPending(null);
    setError(null);
    setHost(health?.duck_host ?? "");
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
    // Reset only when the menu opens, not every time the health poll comes back.
  }, [open]);

  const cls = runtime === "offline" ? "offline" : health?.connected ? "online" : "waiting";
  const tunnelHost = (shown === "duck" ? host.trim() : "") || health?.duck_host || HOST_PLACEHOLDER;
  const command = `scripts/duck-tunnel.sh ${tunnelHost}`;

  async function choose(kind: BackendKind, withHost = "") {
    setBusy(true);
    setError(null);
    const problem = await switchBackend(kind, withHost);
    setBusy(false);
    if (problem) setError(problem);
    else setPending(null);
  }

  function pick(kind: BackendKind) {
    if (kind === "duck") {
      setPending("duck"); // the host comes first; nothing is switched yet
      return;
    }
    setPending(null);
    if (kind !== current) void choose(kind);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* no clipboard (http, locked-down browser): the command is on screen to select */
    }
  }

  const disabled = runtime !== "online" || running || busy;
  const options = ORDER.filter((k) => !health || health.backends.includes(k));

  return (
    <div className="backendmenu" ref={root}>
      <button
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`duckstatus ${cls}`}
        disabled={runtime !== "online"}
        onClick={() => setOpen((o) => !o)}
        title={t("backend.menu.open")}
        type="button"
      >
        <span className="dot" />
        {statusLabel(runtime, health)}
        {runtime === "online" && <Icon name="down" />}
      </button>
      {open && health && (
        <div aria-label={t("backend.menu.title")} className="backendpop" role="dialog">
          <div className="head">
            <div className="title">{t("backend.menu.title")}</div>
            <button className="iconbtn" onClick={() => setOpen(false)} title={t("backend.menu.close")} type="button">
              <Icon name="close" title={t("backend.menu.close")} />
            </button>
          </div>
          {running && <p className="note">{t("backend.menu.running")}</p>}
          <div className="choices" role="radiogroup">
            {options.map((kind) => (
              <button
                aria-checked={shown === kind}
                className="option"
                disabled={disabled}
                key={kind}
                onClick={() => pick(kind)}
                role="radio"
                type="button"
              >
                <span className="name">
                  {t(`backend.${kind}.name`)}
                  {current === kind && <span className="now">{t(health.connected ? "backend.now.connected" : "backend.now.waiting")}</span>}
                </span>
                <span className="desc">{t(`backend.${kind}.summary`)}</span>
                {/* Until microduck_rl#46 is fixed upstream (docs/upstream-notes.md): remove then. */}
                {kind === "sim" && <span className="desc caveat">{t("backend.sim.caveat")}</span>}
              </button>
            ))}
          </div>

          {shown === "duck" && (
            <div className="duckhost">
              <label className="field">
                <span>{t("backend.duck.host")}</span>
                <input
                  autoComplete="off"
                  disabled={disabled}
                  onChange={(e) => setHost(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void choose("duck", host.trim())}
                  placeholder={HOST_PLACEHOLDER}
                  spellCheck={false}
                  value={host}
                />
              </label>
              <p className="meta">{t("backend.duck.tunnel")}</p>
              <div className="command">
                <code>{command}</code>
                <button className="btn small quiet" onClick={() => void copy()} type="button">
                  <Icon name="copy" /> {t(copied ? "backend.copied" : "backend.copy")}
                </button>
              </div>
              <button
                className="btn primary small"
                disabled={disabled || (current === "duck" && host.trim() === (health.duck_host ?? ""))}
                onClick={() => void choose("duck", host.trim())}
                type="button"
              >
                {t(current === "duck" ? "backend.duck.again" : "backend.duck.connect")}
              </button>
            </div>
          )}

          {error && <p className="problem">{error}</p>}
          {!error && pending === null && !health.connected && (
            <>
              <p className="problem">{why(health)}</p>
              {health.backend_error && <p className="meta said">{health.backend_error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function statusLabel(runtime: RuntimeStatus, health: RuntimeHealth | null): string {
  if (runtime === "loading") return t("duck.status.loading");
  if (runtime === "offline" || !health) return t("duck.status.offline");
  return t(`duck.status.${health.backend}.${health.connected ? "connected" : "disconnected"}`);
}

/** The reason in the Studio's language; the backend's own words go below it, smaller. */
function why(health: RuntimeHealth): string {
  if (health.backend === "duck") return t("backend.why.duck");
  if (health.backend === "sim") return t("backend.why.sim");
  return t("backend.why.other");
}

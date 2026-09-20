/**
 * The few glyphs the Studio needs, drawn instead of typed. Emoji render differently on every
 * machine and never match the text around them; these inherit `currentColor` and the font
 * size, so a button looks the same everywhere.
 */
export type IconName =
  | "play"
  | "stop"
  | "eye"
  | "clock"
  | "grip"
  | "close"
  | "up"
  | "down"
  | "plus"
  | "pencil"
  | "sun"
  | "moon"
  | "system"
  | "alert";

const PATHS: Record<IconName, string> = {
  play: "M8 5.5v13l11-6.5z",
  stop: "M7 7h10v10H7z",
  eye: "M12 5.5c-4.2 0-7.4 3-8.6 5.3-.3.5-.3 1 0 1.5C4.6 14.5 7.8 17.5 12 17.5s7.4-3 8.6-5.2c.3-.5.3-1 0-1.5C19.4 8.5 16.2 5.5 12 5.5zm0 9a2.7 2.7 0 1 1 0-5.4 2.7 2.7 0 0 1 0 5.4z",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm.9 4.6v4.7l3.4 2-.9 1.5-4.3-2.6V7.6z",
  grip: "M9 5.5h2v2H9zm4 0h2v2h-2zm-4 5.5h2v2H9zm4 0h2v2h-2zm-4 5.5h2v2H9zm4 0h2v2h-2z",
  close: "m12 10.6 4.4-4.4 1.4 1.4-4.4 4.4 4.4 4.4-1.4 1.4-4.4-4.4-4.4 4.4-1.4-1.4 4.4-4.4-4.4-4.4 1.4-1.4z",
  up: "m12 7 6 7h-4v4h-4v-4H6z",
  down: "m12 18-6-7h4V7h4v4h4z",
  plus: "M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z",
  pencil: "m4 16.6 8.9-8.9 3.4 3.4L7.4 20H4zM14.4 6.2l1.5-1.5a1.2 1.2 0 0 1 1.7 0l1.7 1.7a1.2 1.2 0 0 1 0 1.7l-1.5 1.5z",
  sun: "M12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM11 2h2v3h-2zm0 17h2v3h-2zM2 11h3v2H2zm17 0h3v2h-3zM4.2 5.6l1.4-1.4 2.1 2.1-1.4 1.4zm12.1 12.1 1.4-1.4 2.1 2.1-1.4 1.4zM4.2 18.4l2.1-2.1 1.4 1.4-2.1 2.1zM16.3 6.3l2.1-2.1 1.4 1.4-2.1 2.1z",
  moon: "M20 14.3A8.4 8.4 0 0 1 9.7 4a8.5 8.5 0 1 0 10.3 10.3z",
  system: "M4 5h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-6v2h3v2H7v-2h3v-2H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm1 2v7h14V7z",
  alert: "M12 3.5 22 20H2zm-1 5.5v5h2V9zm0 6.5v2h2v-2z",
};

interface Props {
  name: IconName;
  /** Multiples of the current font size; 1 lines up with the text next to it. */
  size?: number;
  title?: string;
}

export function Icon({ name, size = 1, title }: Props) {
  return (
    <svg
      aria-hidden={title ? undefined : true}
      className="icon"
      focusable="false"
      height={`${size}em`}
      role={title ? "img" : undefined}
      viewBox="0 0 24 24"
      width={`${size}em`}
    >
      {title && <title>{title}</title>}
      <path d={PATHS[name]} fill="currentColor" />
    </svg>
  );
}

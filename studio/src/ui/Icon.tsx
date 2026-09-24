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
  | "undo"
  | "copy"
  | "download"
  | "upload"
  | "redo"
  | "sun"
  | "moon"
  | "system"
  | "alert"
  | "mic";

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
  copy: "M9 3h8a2 2 0 0 1 2 2v10h-2V5H9zm-4 4h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zm0 2v10h8V9z",
  download: "M11 3h2v9h3l-4 5-4-5h3zm-6 15h14v2H5z",
  upload: "M12 3l4 5h-3v9h-2V8H8zm-7 15h14v2H5z",
  undo: "M8 8h4a6 6 0 1 1 0 12h-4v-2h4a4 4 0 0 0 0-8H8v4L2 9l6-5z",
  redo: "M16 8h-4a6 6 0 1 0 0 12h4v-2h-4a4 4 0 0 1 0-8h4v4l6-5-6-5z",
  sun: "M12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM11 2h2v3h-2zm0 17h2v3h-2zM2 11h3v2H2zm17 0h3v2h-3zM4.2 5.6l1.4-1.4 2.1 2.1-1.4 1.4zm12.1 12.1 1.4-1.4 2.1 2.1-1.4 1.4zM4.2 18.4l2.1-2.1 1.4 1.4-2.1 2.1zM16.3 6.3l2.1-2.1 1.4 1.4-2.1 2.1z",
  moon: "M20 14.3A8.4 8.4 0 0 1 9.7 4a8.5 8.5 0 1 0 10.3 10.3z",
  system: "M4 5h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-6v2h3v2H7v-2h3v-2H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm1 2v7h14V7z",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zm-7 9h2a5 5 0 0 0 10 0h2a7 7 0 0 1-6 6.9V21h-2v-2.1A7 7 0 0 1 5 12z",
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

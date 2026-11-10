/* The approved mockup's icon sprite (docs/design/approved-mockup-v7.html), plus lock/copy for sign-in. */
export type IconName =
  | "home" | "list" | "clock" | "gear" | "ext" | "link" | "up" | "down" | "grip" | "pause"
  | "key" | "cloud" | "swap" | "star" | "check" | "alert" | "lock" | "copy" | "dot" | "pulse" | "refresh" | "coin";

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg className={`i${className ? ` ${className}` : ""}`} aria-hidden="true">
      <use href={`#i-${name}`} />
    </svg>
  );
}

/** The Dropwatch logo: the cut stone, full colour (brand/mark/dropwatch-mark.svg, path for path). It replaced
 * the pickaxe glyph in the top bar on 2026-10-10. Decorative: the name always sits beside it. */
export function Mark({ size = 20 }: { size?: number }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <path d="M50 4L96 35.3L77.6 96L22.4 96L4 35.3Z" fill="#1c1405" stroke="#1c1405" strokeWidth={4.5} strokeLinejoin="round" />
      <path d="M50 4L4 35.3L31.6 35.3Z" fill="#d4960f" />
      <path d="M50 4L31.6 35.3L68.4 35.3Z" fill="#ffd978" />
      <path d="M50 4L68.4 35.3L96 35.3Z" fill="#c98a0b" />
      <path d="M4 35.3L31.6 35.3L22.4 96Z" fill="#8a5e05" />
      <path d="M31.6 35.3L68.4 35.3L77.6 96L22.4 96Z" fill="#f2b632" />
      <path d="M68.4 35.3L96 35.3L77.6 96Z" fill="#a8700a" />
      <path d="M50 4L31.6 35.3L42 35.3Z" fill="#fff3c4" opacity={0.6} />
      <path d="M4 35.3L96 35.3" stroke="#ffe9a8" strokeWidth={1.2} opacity={0.6} />
    </svg>
  );
}

const s = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <symbol id="i-home" viewBox="0 0 24 24" {...s}><path d="M3 11 12 4l9 7" /><path d="M5 10v10h14V10" /></symbol>
      <symbol id="i-list" viewBox="0 0 24 24" {...s}><path d="M10 6h10M10 12h10M10 18h10" /><path d="M4 6h1M4 12h1M4 18h1" /></symbol>
      <symbol id="i-clock" viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></symbol>
      <symbol id="i-coin" viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="9" /><path d="M12 7.5 15 12l-3 4.5L9 12z" /></symbol>
      <symbol id="i-pulse" viewBox="0 0 24 24" {...s}><path d="M3 12h4l3-7 4 14 3-7h4" /></symbol>
      <symbol id="i-refresh" viewBox="0 0 24 24" {...s}><path d="M20 11a8 8 0 0 0-14.8-4M4 13a8 8 0 0 0 14.8 4" /><path d="M5 3v4h4M19 21v-4h-4" /></symbol>
      <symbol id="i-gear" viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></symbol>
      <symbol id="i-ext" viewBox="0 0 24 24" {...s}><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></symbol>
      <symbol id="i-link" viewBox="0 0 24 24" {...s}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></symbol>
      <symbol id="i-up" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="m6 15 6-6 6 6" /></symbol>
      <symbol id="i-down" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="m6 9 6 6 6-6" /></symbol>
      <symbol id="i-grip" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.6" /><circle cx="15" cy="6" r="1.6" /><circle cx="9" cy="12" r="1.6" /><circle cx="15" cy="12" r="1.6" /><circle cx="9" cy="18" r="1.6" /><circle cx="15" cy="18" r="1.6" /></symbol>
      <symbol id="i-pause" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="M9 5v14M15 5v14" /></symbol>
      <symbol id="i-key" viewBox="0 0 24 24" {...s}><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9M17 6l3 3M15 8l2 2" /></symbol>
      <symbol id="i-cloud" viewBox="0 0 24 24" {...s}><path d="M7 18a5 5 0 1 1 .9-9.9A6 6 0 0 1 19 10a4 4 0 0 1 0 8z" /><path d="m4 4 16 16" /></symbol>
      <symbol id="i-swap" viewBox="0 0 24 24" {...s}><path d="M4 8h13l-3-3M20 16H7l3 3" /></symbol>
      <symbol id="i-star" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z" /></symbol>
      <symbol id="i-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></symbol>
      <symbol id="i-alert" viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 16.5v.5" /></symbol>
      <symbol id="i-lock" viewBox="0 0 24 24" {...s}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></symbol>
      <symbol id="i-copy" viewBox="0 0 24 24" {...s}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></symbol>
      <symbol id="i-dot" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx="12" cy="12" r="8" /></symbol>
    </svg>
  );
}

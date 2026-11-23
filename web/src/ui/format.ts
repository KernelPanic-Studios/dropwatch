/* Formatting rules carried over from the approved mockup: non-breaking spaces between numbers and
 * units (spec §11), "1 h 51 min", "Fri 16 Oct", 24-hour clock times. */
export const NB = " ";

export function dur(min: number): string {
  const m = Math.max(0, Math.round(min));
  if (m < 60) return `${m}${NB}min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h}${NB}h ${r}${NB}min` : `${h}${NB}h`;
}

/** A milestone label on the track: "30 min", "1 h", "1.5 h". */
export function mark(min: number): string {
  if (min < 60) return `${min}${NB}min`;
  const h = min / 60;
  return `${Number.isInteger(h) ? h : h.toFixed(1)}${NB}h`;
}

const DAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" });
const TIME = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });

/** "Fri 16 Oct" in the viewer's own time zone. */
export const day = (d: Date | string) => DAY.format(new Date(d)).replace(",", "");
/** "23:15" in the viewer's own time zone. */
export const clock = (d: Date | string) => TIME.format(new Date(d));

/** Whole minutes from now until d (never negative). */
export function minutesUntil(d: Date | string, now = new Date()): number {
  return Math.max(0, Math.round((new Date(d).getTime() - now.getTime()) / 60_000));
}

/** "2 d 4 h" style span for long deadlines, minutes below an hour. */
export function span(min: number): string {
  if (min < 60 * 24) return dur(min);
  const d = Math.floor(min / (60 * 24));
  const h = Math.floor((min % (60 * 24)) / 60);
  return h ? `${d}${NB}d ${h}${NB}h` : `${d}${NB}d`;
}

/** Twitch box art at the size the page draws (the API strips the size; both forms are served). */
export function boxArt(url: string): string {
  if (!url) return "";
  if (url.startsWith("api/img/")) return url; // a kept copy (images.py), already 144x192
  if (url.includes("{width}x{height}")) return url.replace("{width}x{height}", "144x192");
  if (/-\d+x\d+\.\w+$/.test(url)) return url.replace(/-\d+x\d+(\.\w+)$/, "-144x192$1");
  return url.replace(/(\.\w+)$/, "-144x192$1");
}

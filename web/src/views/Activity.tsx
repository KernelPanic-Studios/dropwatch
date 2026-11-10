import { useEffect, useState, type ReactNode } from "react";
import { api, type Activity, type ActivityEvent } from "../api/client";
import { useApp } from "../store";
import { clock, day } from "../ui/format";

/** Activity (approved mockup docs/design/pre-docker-mockup.html, 2026-10-10): what Dropwatch did, newest
 * first, one plain sentence per event, grouped by the viewer's day. The server keeps 7 days (store.py). */
type Group = "mining" | "twitch" | "rewards" | "problems" | "notifications";
/** Multi-select (asked for 2026-10-10): every kind starts on; turn off the ones you don't care about. */
const GROUPS: [Group, string][] = [
  ["mining", "Mining"], ["twitch", "Twitch"], ["rewards", "Rewards"], ["problems", "Problems"], ["notifications", "Notifications"],
];
const ALL = GROUPS.map(([g]) => g);
const SHOWN_KEY = "dropwatch.activity.shown"; // this browser's choice

function savedShown(): Set<Group> {
  try {
    const raw = JSON.parse(localStorage.getItem(SHOWN_KEY) ?? "null");
    if (Array.isArray(raw)) return new Set(raw.filter((g): g is Group => (ALL as string[]).includes(g)));
  } catch { /* storage blocked or unreadable: show everything */ }
  return new Set(ALL);
}

function saveShown(shown: Set<Group>) {
  try { localStorage.setItem(SHOWN_KEY, JSON.stringify([...shown])); } catch { /* storage blocked: not remembered */ }
}

export interface Line { text: ReactNode; d?: string; tone: "ok" | "gold" | "bad" | "note" | ""; group: Group }

const s = (v: unknown) => (typeof v === "string" ? v : "");
const QUIET = new Set(["mining", "switched"]);

function why(d: ActivityEvent["data"]): string {
  if (d.from_live === false) return `${s(d.from)} went offline`;
  const r = s(d.reason);
  if (r === "you picked it") return "You picked it";
  if (r === "you pinned it") return "Pinned in Up next";
  if (r === "watch streak") return "Watch-streak visit to a favourite";
  if (r.startsWith("priority ")) return `Priority ${r.slice(9)}`;
  if (r === "most urgent") return d.channel_reason === "favourite" ? "A favourite channel came online" : "Most urgent campaign";
  return "";
}

/** One event as a sentence, or null for one that only repeats what the line before it said. `older` is the
 * event logged just before it. */
export function describe(e: ActivityEvent, older: ActivityEvent | undefined): Line | null {
  const d = e.data;
  switch (e.kind) {
    case "started":
      return { text: <>Dropwatch started{d.commit ? <> <span className="mono">{s(d.commit)}</span></> : null}</>,
        d: d.version ? `Version ${s(d.version)}` : undefined, tone: "", group: "mining" };
    case "state": {
      const st = s(d.state);
      if (st === "switched") return null; // the switched event says it
      if (st === "mining") {
        if (older && (older.kind === "switched" || (older.kind === "state" && QUIET.has(s(older.data.state))))) return null;
        return { text: older?.kind === "state" ? "Mining again" : "Mining", tone: "ok", group: "mining" };
      }
      if (older?.kind === "state" && s(older.data.state) === st) return null;
      if (st === "idle") return { text: "Nothing to mine: none of your campaigns has a live channel", tone: "", group: "mining" };
      if (st === "paused") return { text: "Paused", tone: "", group: "mining" };
      if (st === "twitch_unreachable") return { text: "Couldn't reach Twitch", d: s(d.error) || undefined, tone: "bad", group: "problems" };
      if (st === "signed_out") return { text: "Signed out of Twitch", tone: "bad", group: "problems" };
      return null;
    }
    case "switched": {
      const game = s(d.game);
      const parts = [why(d), game && (d.campaign ? `${game} · ${s(d.campaign)}` : game)].filter(Boolean);
      return { text: <>Switched to <b>{s(d.to)}</b> from {s(d.from)}</>, d: parts.join(" · ") || undefined, tone: "note", group: "mining" };
    }
    case "claimed":
      return { text: <>Claimed <b>{s(d.reward)}</b> from {s(d.campaign)}</>, d: s(d.game) || undefined, tone: "ok", group: "rewards" };
    case "claim_failed":
      return { text: <>Couldn't claim a reward from {s(d.campaign)}</>, d: "Twitch turned it down", tone: "bad", group: "problems" };
    case "needs_you":
      return { text: <>{s(d.campaign)} may need its game account linked</>, tone: "bad", group: "problems" };
    case "channel_dropped":
      return { text: <>Stopped watching <b>{s(d.channel)}</b>: its stream wouldn't play</>, tone: "bad", group: "problems" };
    case "points_claimed":
      return { text: d.channel ? <>Opened a channel points chest on <b>{s(d.channel)}</b></> : "Opened a channel points chest",
        tone: "gold", group: "rewards" };
    case "points_claim_failed":
      return { text: d.channel ? <>Couldn't open a channel points chest on <b>{s(d.channel)}</b></> : "Couldn't open a channel points chest",
        tone: "bad", group: "problems" };
    case "points_watch":
      return d.on
        ? { text: <>Started watching <b>{s(d.channel)}</b> for channel points</>, d: s(d.game) || undefined, tone: "gold", group: "rewards" }
        : { text: <>Stopped watching <b>{s(d.channel)}</b> for channel points</>, tone: "", group: "rewards" };
    case "points_dropped":
      return { text: <>Stopped watching <b>{s(d.channel)}</b> for channel points: its stream wouldn't play</>, tone: "bad", group: "problems" };
    case "points_earned": {
      const reason = s(d.reason) === "WATCH_STREAK" ? "watch-streak " : s(d.reason) === "RAID" ? "raid " : "";
      return { text: `Earned ${typeof d.points === "number" ? d.points : ""} ${reason}points${d.channel ? ` on ${s(d.channel)}` : ""}`,
        tone: "gold", group: "rewards" };
    }
    case "checked": {
      const linked = Array.isArray(d.linked) ? d.linked : [];
      const parts = [
        typeof d.campaigns === "number" ? `${d.campaigns} campaigns` : "",
        typeof d.new === "number" && d.new > 0 ? `${d.new} new` : "",
        ...linked.map((g) => `${g} now linked`),
        typeof d.seconds === "number" ? `took ${d.seconds} s` : "",
      ].filter(Boolean);
      return { text: d.manual ? "You checked Twitch" : "Checked Twitch for campaign changes", d: parts.join(" · ") || undefined,
        tone: "", group: "twitch" };
    }
    case "notified": {
      const title = s(d.title).replace(/^Dropwatch: /, "");
      const sent = Array.isArray(d.sent) ? d.sent : [];
      const failed = Array.isArray(d.failed) ? d.failed : [];
      return sent.length
        ? { text: <>Sent “{title}” to {sent.join(", ")}</>, d: failed.length ? `Couldn't reach ${failed.join(", ")}` : undefined,
          tone: "", group: "notifications" }
        : { text: <>Couldn't send “{title}”</>, d: failed.length ? `Tried ${failed.join(", ")}` : undefined, tone: "bad", group: "notifications" };
    }
    default:
      return null;
  }
}

export function ActivityView() {
  const { state } = useApp();
  const [data, setData] = useState<Activity | null>(null);
  const [shown, setShown] = useState<Set<Group>>(savedShown);
  const choose = (next: Set<Group>) => { setShown(next); saveShown(next); };
  const toggle = (g: Group) => { const n = new Set(shown); if (n.has(g)) n.delete(g); else n.add(g); choose(n); };
  useEffect(() => {
    let live = true;
    api.get<Activity>("/activity").then((a) => { if (live) setData(a); }).catch(() => undefined);
    return () => { live = false; };
  }, [state]); // every live event re-reads the state: re-read Activity with it

  const lines: { e: ActivityEvent; line: Line }[] = [];
  const events = data?.events ?? [];
  events.forEach((e, i) => {
    const line = describe(e, events[i + 1]);
    if (line && shown.has(line.group)) lines.push({ e, line });
  });
  const rows: ReactNode[] = [];
  let lastDay = "";
  for (const [i, { e, line }] of lines.entries()) {
    const label = day(e.at);
    if (label !== lastDay) { rows.push(<div className="day" key={`d-${label}`}>{label}</div>); lastDay = label; }
    rows.push(
      <div className="act" key={`${i}-${e.at}-${e.kind}`}>
        <span className="t">{clock(e.at)}</span><span className={`adot ${line.tone}`} aria-hidden="true" />
        <div><div className="s">{line.text}</div>{line.d && <div className="d">{line.d}</div>}</div>
      </div>,
    );
  }
  return (
    <section className="view" id="v-activity" aria-labelledby="h-activity">
      <div className="view-h">
        <h1 id="h-activity" className="disp" tabIndex={-1}>Activity</h1>
        <div className="chips" role="group" aria-label="Show">
          <button type="button" aria-pressed={shown.size === ALL.length} onClick={() => choose(new Set(ALL))}>All</button>
          {GROUPS.map(([g, label]) => (
            <button key={g} type="button" aria-pressed={shown.has(g)} onClick={() => toggle(g)}>{label}</button>
          ))}
        </div>
      </div>
      {!data && <p className="lead">Loading…</p>}
      {data && rows.length > 0 && <div className="list act-list">{rows}</div>}
      {data && !rows.length && <p className="hint">{!shown.size ? "Turn on at least one kind to see activity."
        : shown.size === ALL.length ? "Nothing yet." : `Nothing like that in the last ${data.kept_days} days.`}</p>}
      {data && <p className="keep">Kept for {data.kept_days} days.</p>}
    </section>
  );
}

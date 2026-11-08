import { useEffect, useState, type ReactNode } from "react";
import { api, type Campaign, type Lists, type State } from "../api/client";
import { useLists } from "../lists";
import { go } from "../router";
import { useApp } from "../store";
import { NB, boxArt, clock, day, dur, mark, minutesUntil, span } from "../ui/format";
import { Icon } from "../ui/Icons";
import { MenuButton } from "./Menu";
import { UpNext } from "./UpNext";
import { Track, milestones } from "./Track";

/** Overview (approved mockup): banner, Mining now (or the idle card), Needs you, Up next, Done.
 * On phones Needs you comes first in the DOM too, so screen readers get the same order. */
export function OverviewView() {
  const { state, connection, lostSince } = useApp();
  const { lists, save } = useLists();
  const phone = useNarrow();
  const { say, sayError } = useApp();
  if (!state) {
    return (
      <section className="view" aria-labelledby="h-overview"><h1 className="sr" id="h-overview" tabIndex={-1}>Overview</h1>
        {connection === "lost" && <LostBanner lostSince={lostSince} />}</section>
    );
  }
  const lost = connection === "lost";
  const priorityOf = (game: string, ordinal = false) => {
    const i = lists?.priority.indexOf(game) ?? -1;
    if (i < 0) return null;
    return ordinal ? `${nth(i + 1)} in Priority` : `Priority ${i + 1}`;
  };
  /** Undo reverses only this one change, on the lists as they are now (they may have changed meanwhile). */
  async function undoOn(change: (now: Lists) => Lists, done: string) {
    try {
      const now = await api.get<Lists>("/lists");
      const err = await save(change(now));
      say(err ? { title: "Couldn't undo", detail: err, tone: "bad" } : { title: "Undone", detail: done });
    } catch (e) { sayError(e, "Couldn't undo"); }
  }
  async function never(game: string) {
    if (!lists) return;
    const at = lists.priority.indexOf(game);  // to put it back where it was
    const msg = await save({ ...lists, priority: lists.priority.filter((g) => g !== game), never: [...lists.never, game] });
    if (msg) { say({ title: "Couldn't move it to Never", detail: msg, tone: "bad" }); return; }
    say({ title: "Moved to Never", detail: `${game} won't be mined.` }, () => void undoOn((now) => {
      const priority = now.priority.filter((g) => g !== game);
      if (at >= 0) priority.splice(Math.min(at, priority.length), 0, game);
      return { ...now, never: now.never.filter((g) => g !== game), priority };
    }, `${game} can be mined again.`));
  }
  async function prioritise(game: string) {
    if (!lists) return;
    const wasNever = lists.never.includes(game);
    const priority = [...lists.priority.filter((g) => g !== game), game];
    const msg = await save({ ...lists, priority, never: lists.never.filter((g) => g !== game) });
    if (msg) { say({ title: "Couldn't add it to Priority", detail: msg, tone: "bad" }); return; }
    say({ title: "Added to Priority", detail: `${game} is number ${priority.length}.` }, () => void undoOn((now) => ({
      ...now, priority: now.priority.filter((g) => g !== game),
      never: wasNever && !now.never.includes(game) ? [...now.never, game] : now.never,
    }), `${game} is off Priority.`));
  }
  const needs = <NeedsYou key="needs" state={state} onNever={never} />;
  const now = <NowSlot key="now" state={state} lost={lost} lostSince={lostSince} priorityOf={priorityOf}
    priority={lists ? lists.priority : null} />;
  return (
    <section className="view" id="v-overview" aria-labelledby="h-overview">
      <h1 className="sr" id="h-overview" tabIndex={-1}>Overview</h1>
      <Banner state={state} lost={lost} lostSince={lostSince} />
      {phone ? [needs, now] : [now, needs]}
      <PointsNote state={state} />
      <UpNext state={state} priorityOf={priorityOf} onNever={never} onPriority={prioritise} />
      <Done state={state} />
    </section>
  );
}

function useNarrow() {
  const q = "(max-width: 720px)";
  const [m, setM] = useState(() => typeof matchMedia === "function" && matchMedia(q).matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(q);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return m;
}

/** Channel points: who is watched alongside drops right now (the Channel points page has the rest). */
export function PointsNote({ state }: { state: State }) {
  const w = state.points_watching ?? [];
  if (!w.length) return null;
  return (
    <p className="points-note" role="status"><Icon name="coin" />
      <span>{state.current ? "Also watching" : "Watching"} {w.map((p, i) => <span key={p.channel}>{i ? " and " : ""}<b>{p.channel}</b></span>)} for channel points.{" "}
        <a href="#points">Channel points</a></span>
    </p>
  );
}

/* ---------- banner (one at a time, most serious first) ---------- */
function LostBanner({ lostSince }: { lostSince: Date | null }) {
  const { refreshState } = useApp();
  return (
    <div className="banner" data-tone="alert" role="alert"><Icon name="cloud" />
      <div><div className="banner-t">Can't reach the miner</div>
        <div className="banner-b">No answer{lostSince ? ` since ${clock(lostSince)}` : ""}. Anything below is what it was doing then. This page keeps trying by itself.</div></div>
      <div className="banner-acts"><button className="btn" type="button" onClick={() => void refreshState()}>Retry now</button></div>
    </div>
  );
}

function Banner({ state, lost, lostSince }: { state: State; lost: boolean; lostSince: Date | null }) {
  const { refreshState, say, sayError } = useApp();
  if (lost) return <LostBanner lostSince={lostSince} />;
  if (state.state === "signed_out") {
    return (
      <div className="banner" data-tone="alert" role="alert"><Icon name="key" />
        <div><div className="banner-t">Twitch signed you out</div>
          <div className="banner-b">Mining is stopped until you sign in again. Drop progress is kept.</div></div>
        <div className="banner-acts"><button className="btn strong" type="button" onClick={() => go("connect")}><Icon name="key" />Get a sign-in code</button></div>
      </div>
    );
  }
  if (state.state === "paused") {
    const until = state.paused_until;
    return (
      <div className="banner" role="status"><Icon name="pause" />
        <div><div className="banner-t">{until ? `Paused until ${clock(until)}` : "Paused until you resume"}</div>
          <div className="banner-b">{until ? `Nothing is being mined for the next ${dur(minutesUntil(until))}. ` : "Nothing is being mined. "}Progress is kept.</div></div>
        <div className="banner-acts"><button className="btn strong" type="button" onClick={async () => {
          try { await api.post("/resume"); say("Mining resumed."); }
          catch (e) { sayError(e, "Couldn't resume"); }
          void refreshState();
        }}>Resume now</button></div>
      </div>
    );
  }
  if (state.state === "twitch_unreachable") {
    return (
      <div className="banner" data-tone="alert" role="alert"><Icon name="cloud" />
        <div><div className="banner-t">Can't reach Twitch</div>
          <div className="banner-b">The miner keeps retrying{state.next_check_at ? ` (next try at ${clock(state.next_check_at)})` : ""}. Progress so far is kept.</div></div>
      </div>
    );
  }
  const cat = state.catalog;
  if (cat && cat.status !== "ok") {
    return (
      <div className="banner" data-tone="warn" role="status"><Icon name="cloud" />
        <div><div className="banner-t">{cat.status === "stale" ? "The campaign list hasn't updated" : "Can't reach the campaign list"}{cat.since ? ` since ${clock(cat.since)}` : ""}</div>
          <div className="banner-b">Campaigns you've started keep mining. New campaigns show up again once the list is back. Checking every 5 minutes.</div></div>
      </div>
    );
  }
  return null;
}

/* ---------- Mining now ---------- */
function NowSlot({ state, lost, lostSince, priorityOf, priority }: { state: State; lost: boolean; lostSince: Date | null; priorityOf: (g: string, ordinal?: boolean) => string | null; priority: string[] | null }) {
  const cur = state.current;
  if (state.state === "signed_out") {
    return (
      <section aria-labelledby="h-now-out"><h2 className="sec-h" id="h-now-out">Mining now</h2>
        <div className="empty">Nothing is being mined while you're signed out of Twitch.</div></section>
    );
  }
  if (state.streak_visit) return <StreakVisit visit={state.streak_visit} next={cur?.campaign.name ?? null} />;
  if (!cur) return state.priority_only ? <PriorityIdle state={state} priority={priority} /> : <Idle state={state} />;
  return <NowCard state={state} lost={lost} lostSince={lostSince} priorityOf={priorityOf} />;
}

/** A watch-streak visit (Settings > Mining): drops wait a few minutes while a favourite's new stream is watched. */
function StreakVisit({ visit, next }: { visit: NonNullable<State["streak_visit"]>; next: string | null }) {
  const { refreshState, say, sayError } = useApp();
  const [busy, setBusy] = useState(false);
  return (
    <section className="idle" aria-labelledby="h-streak">
      <h2 id="h-streak">Mining now</h2>
      <p>Watching <b>{visit.channel}</b> for its watch streak. Back to drops by {clock(visit.until)}
        {next ? `, starting with ${next}` : ""}.</p>
      <div className="acts"><button className="btn" type="button" aria-disabled={busy} onClick={async () => {
        if (busy) return;
        setBusy(true);
        try { await api.post("/streak/end"); say("Back to drops."); }
        catch (e) { sayError(e, "Couldn't stop the visit"); }
        finally { setBusy(false); void refreshState(); }
      }}>Back to drops now</button></div>
    </section>
  );
}

const VERDICT: Record<string, [string, string]> = {
  plenty: ["green", "Plenty of time"], tight: ["warn", "Tight on time"], wont_finish: ["red", "Won't finish in time"],
};

function NowCard({ state, lost, lostSince, priorityOf }: { state: State; lost: boolean; lostSince: Date | null; priorityOf: (g: string, ordinal?: boolean) => string | null }) {
  const { say, sayError, refreshState } = useApp();
  const [allOpen, setAllOpen] = useState(false);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const cur = state.current!;
  const c = cur.campaign;
  const { ms, watched: w, max, nextIdx } = milestones(c.drops);
  const nx = ms[nextIdx];
  const mining = !lost && (state.state === "mining" || state.state === "switched");
  const status = state.state === "paused" ? <span className="chip"><Icon name="pause" />Paused · progress kept</span>
    : lost ? <span className="chip">Last known · {lostSince ? clock(lostSince) : ""}</span>
    : state.state === "twitch_unreachable" ? <span className="chip">Retrying Twitch · progress kept</span>
    : <span className="chip gold"><span className="live" aria-hidden="true" />Mining</span>;
  const leftMin = minutesUntil(c.ends_at);
  const toGo = c.minutes_needed;
  const ratio = leftMin > 0 ? toGo / leftMin : 2;
  const fit = VERDICT[c.verdict ?? ""] ?? VERDICT.plenty!;
  const sw = state.last_switch;
  const swKey = sw ? `${sw.from}>${sw.to}@${sw.at}` : null;
  const reason = cur.reason === "you picked it" ? "You picked it" : priorityOf(c.game, true) ?? cap(cur.reason);

  async function pause(minutes: number | null) {
    try { await api.post("/pause", { minutes }); say("Paused. Progress is kept."); }
    catch (e) { sayError(e, "Couldn't pause"); }
    void refreshState();
  }
  async function useChannel(login: string) {
    try { await api.post("/channel", { login }); say(`Switched to ${login}`); }
    catch (e) { sayError(e, "Couldn't switch channel"); }
    void refreshState();
  }

  return (
    <article className={`now${mining ? "" : " dim"}`} aria-labelledby="h-now" style={{ ["--art-bg" as string]: `url(${boxArt(c.box_art_url)})` }}>
      <img className="box" src={boxArt(c.box_art_url)} alt="" />
      <div className="now-main">
        <div className="now-head">
          <div className="now-title">
            <div className="now-title-row"><h2 id="h-now"><span className="sr">Mining now: </span>{c.name}</h2>{status}
              <span className="chip" title="Why this campaign is being mined"><span className="sr">Why: </span>{reason}</span></div>
            {/* Nick's pick 2026-10-10 (docs/design/now-reason-options.html): reason as a chip (A), facts labelled (C) */}
            <div className="now-facts">
              <span><span className="k">Game</span><b>{c.game}</b></span>
              <span><span className="k">{mining ? "Channel" : "Last on"}</span><b>{cur.channel.login}</b>
                {cur.channel.favourite && <> <span className="fav-mark"><Icon name="star" />favourite</span></>}
                {mining && cur.channels.length > 0 && (
                  <> · <MenuButton id="ch-menu" label="Watch instead" wrapClass="ch-pick" buttonClass="link" buttonLabel="Change channel"
                    buttonContent="change" items={cur.channels.map((ch) => ({
                      key: ch.login, onSelect: () => void useChannel(ch.login),
                      content: <>{ch.favourite && <Icon name="star" />}{ch.login}<span className="v">{ch.viewers.toLocaleString()} watching</span></>,
                    }))} /></>
                )}</span>
            </div>
          </div>
          <span className="ends">Ends {day(c.ends_at)}</span>
        </div>
        {sw && swKey !== dismissed && (
          <div className="notice" role="status"><Icon name="swap" />
            <span>Switched from <b>{sw.from}</b> to <b>{sw.to}</b> at {clock(sw.at)}. Progress carried over.</span>
            <button className="btn quiet" type="button" onClick={() => setDismissed(swKey)}>Dismiss</button></div>
        )}
        {max > 0 && <Track ms={ms} watched={w} max={max} nextIdx={nextIdx}
          label={`${w} of ${max} minutes watched.${nx ? ` ${dur(nx.at - w)} to the next reward.` : ""}`} />}
        {nx && (
          <div className="next-card">
            <div className="arts">{nx.items.map((it, i) => <img key={i} src={it.image} alt="" />)}</div>
            <div><div className="next-when">{mining ? `Next reward in ${dur(nx.at - w)} (~${clock(new Date(Date.now() + (nx.at - w) * 60_000))})` : `${dur(nx.at - w)} of watching to the next reward`}</div>
              <div className="next-what">{nx.items.map((i) => i.name).join(", ")}</div></div>
          </div>
        )}
        <button className="btn quiet more" type="button" aria-expanded={allOpen} aria-controls="all-ms" onClick={() => setAllOpen(!allOpen)}>
          {allOpen ? "Hide" : "Show"} all {ms.length} rewards<Icon name="down" className="chev" /></button>
        <div className="all-ms" id="all-ms" hidden={!allOpen}>
          {ms.map((m, i) => (
            <div key={m.at} className={`m ${m.at <= w ? "got" : i === nextIdx ? "next" : ""}`}>
              <span className="when">{mark(m.at)}</span><span>{m.items.map((x) => x.name).join(", ")}</span>
              <span className="st">{m.at <= w ? "Claimed" : i === nextIdx ? `Next, ${dur(m.at - w)} to go` : `${dur(m.at - w)} to go`}</span>
            </div>
          ))}
        </div>
        <div className="now-foot">
          <div className="watched"><b className="wnum">{w} / {max}{NB}min</b> watched</div>
          <div className="deadline"><span className={`chip ${fit[0]}`}>{fit[1]}</span>
            <div className="dl-bar" aria-hidden="true"><span style={{ width: `${Math.max(1.5, Math.min(100, ratio * 100))}%` }} /></div>
            <span className="dl-lab"><b>{dur(toGo)}</b> of watching needed · <b>{span(leftMin)}</b> left</span></div>
          {mining && (
            <MenuButton id="pause-menu" label="Pause for" buttonContent={<><Icon name="pause" />Pause</>}
              items={[["30 min", 30], ["1 h", 60], ["4 h", 240], ["Until I resume", null]].map(([t, m]) => ({
                key: String(t), content: String(t).replace(" ", NB), onSelect: () => void pause(m as number | null),
              }))} />
          )}
        </div>
      </div>
    </article>
  );
}

function Idle({ state }: { state: State }) {
  const { refreshState, say, sayError } = useApp();
  const [busy, setBusy] = useState(false);
  const line = state.first_in_line;
  const next = state.next_check_at ? minutesUntil(state.next_check_at) : null;
  return (
    <section className="idle" aria-labelledby="h-idle">
      <h2 id="h-idle">Nothing to mine right now</h2>
      <p>None of your campaigns has a live channel with drops turned on.
        {line.length ? ` ${line[0]} is first in line${line[1] ? `, then ${line[1]}` : ""}.` : ""}
        {next !== null ? ` Checking again in ${dur(Math.max(1, next))}.` : ""}</p>
      <div className="acts"><button className="btn" type="button" aria-disabled={busy} onClick={async () => {
        if (busy) return;
        setBusy(true);
        try { await api.post("/refresh"); say("Checked for live channels."); }
        catch (e) { sayError(e, "Couldn't check"); }
        finally { setBusy(false); void refreshState(); }
      }}>Check now</button></div>
    </section>
  );
}

/** Priority only, nothing being mined: nothing in the Priority games can be mined (no campaign, or it needs a
 * link, or hasn't started), or a Priority campaign is waiting for someone to go live (approved mockup
 * 2026-10-12; the first heading softened after review, since the planner can't tell those apart).
 * priority is null until the lists have loaded. */
function PriorityIdle({ state, priority }: { state: State; priority: string[] | null }) {
  const { refreshState, say, sayError } = useApp();
  const [busy, setBusy] = useState(false);
  const line = state.first_in_line;
  const next = state.next_check_at ? minutesUntil(state.next_check_at) : null;
  const names = !priority?.length ? "" : priority.length > 1 ? `${priority.slice(0, -1).join(", ")} and ${priority.at(-1)}` : priority[0];
  async function setPriorityOnly(on: boolean) {
    try {
      await api.put("/settings", { priority_only: on });
      if (!on) say({ title: "Priority only is off", detail: "Every game can be mined again." }, () => void setPriorityOnly(true));
      else say("Priority only is back on");
    } catch (e) { sayError(e, "Couldn't change it"); }
    void refreshState();
  }
  const off = <button className="btn quiet" type="button" onClick={() => void setPriorityOnly(false)}>Turn off Priority only</button>;
  if (!line.length) {
    return (
      <section className="idle" aria-labelledby="h-idle">
        <h2 id="h-idle">Nothing to mine in your Priority games</h2>
        <p>Priority only is on, so other games aren't mined.{" "}
          {priority === null ? "" : priority.length ? `${names} ${priority.length === 1 ? "has" : "have"} nothing Dropwatch can mine right now.`
            : "Your Priority list is empty."}</p>
        <div className="acts"><button className="btn" type="button" onClick={() => go("priorities")}>Edit Priority</button>{off}</div>
      </section>
    );
  }
  return (
    <section className="idle" aria-labelledby="h-idle">
      <h2 id="h-idle">Waiting for a Priority game to go live</h2>
      <p>Priority only is on, so other games aren't mined. {line[0]} is first in line{line[1] ? `, then ${line[1]}` : ""}.
        {next !== null ? ` Checking again in ${dur(Math.max(1, next))}.` : ""}</p>
      <div className="acts"><button className="btn" type="button" aria-disabled={busy} onClick={async () => {
        if (busy) return;
        setBusy(true);
        try { await api.post("/refresh"); say("Checked for live channels."); }
        catch (e) { sayError(e, "Couldn't check"); }
        finally { setBusy(false); void refreshState(); }
      }}>Check now</button>{off}</div>
    </section>
  );
}

/* ---------- lists ---------- */
function Sec({ id, title, count, aside, children }: { id: string; title: string; count: number; aside?: string; children: ReactNode }) {
  return (
    <section id={`sec-${id}`} aria-labelledby={`h-${id}`}>
      <div className="sec-h"><h2 id={`h-${id}`}>{title}</h2><span className="count">{count}</span>{aside && <span className="aside">{aside}</span>}</div>
      {children}
    </section>
  );
}

function firstReward(c: Campaign) {
  const d = [...c.drops].filter((x) => !x.claimed && x.rewards.length).sort((a, b) => a.required_minutes - b.required_minutes)[0];
  return d ? { name: d.rewards[0]!.name, img: d.rewards[0]!.image_url, at: d.required_minutes, all: d.rewards } : null;
}

/** Needs you, with Ignore (approved 2026-10-11, docs/design/ignore-mockup.html): Ignore hides one campaign until
 * it ends, and with it its alert and its weekly-summary mention (the server leaves it out of Needs you). */
function NeedsYou({ state, onNever }: { state: State; onNever: (game: string) => void }) {
  const { refreshState, say, sayError } = useApp();
  const [showIgnored, setShowIgnored] = useState(false);
  const ignored = state.needs_ignored ?? [];
  if (!state.needs_you.length && !ignored.length) return null;

  async function unignore(c: Campaign, done: { title: string; detail: string }) {
    try { await api.del(`/needs/ignored/${encodeURIComponent(c.id)}`); say(done); }
    catch (e) { sayError(e, "Couldn't bring it back"); }
    void refreshState();
  }
  async function ignore(c: Campaign) {
    try {
      await api.post(`/needs/ignored/${encodeURIComponent(c.id)}`);
      say({ title: "Ignored", detail: `${c.name} won't show here or in alerts. It ends ${day(c.ends_at)}.` },
        () => void unignore(c, { title: "Undone", detail: `${c.name} is back in Needs you.` }));
    } catch (e) { sayError(e, "Couldn't ignore it"); }
    void refreshState();
  }

  const label = `${ignored.length} ignored · ${showIgnored ? "Hide" : "Show"}`;
  const toggle = (solo: boolean) => (
    <button className={`ign-foot${solo ? " solo" : ""}`} type="button" aria-expanded={showIgnored} aria-controls="needs-ignored"
      aria-label={solo ? `Needs you · ${label}` : label} onClick={() => setShowIgnored(!showIgnored)}>
      {solo && <><b>Needs you</b><span className="sep">·</span></>}
      {ignored.length} ignored<span className="sep">·</span><u>{showIgnored ? "Hide" : "Show"}</u>
    </button>
  );
  const ignoredRows = showIgnored && (
    <div id="needs-ignored">
      {ignored.map((c) => (
        <div className="row ign" key={c.id}>
          <img className="box" src={boxArt(c.box_art_url)} alt="" />
          <div>
            <div className="row-t">{c.maybe_unlinked ? `${c.game} may need linking` : `Link your ${c.game} account`}</div>
            <div className="row-s">{c.name}<span className="sep">·</span>ends {day(c.ends_at)}</div>
          </div>
          <div className="row-acts">
            <button className="btn quiet" type="button" aria-label={`Unignore ${c.name}`}
              onClick={() => void unignore(c, { title: "Back in Needs you", detail: c.name })}>Unignore</button>
          </div>
        </div>
      ))}
    </div>
  );

  if (!state.needs_you.length) {
    return (
      <section id="sec-needs" aria-label="Needs you" className="ign-only">
        {toggle(true)}
        {ignoredRows && <div className="list needs">{ignoredRows}</div>}
      </section>
    );
  }
  return (
    <Sec id="needs" title="Needs you" count={state.needs_you.length} aside="Can't be mined until you act">
      <div className="list needs">
        {state.needs_you.map((c) => {
          const r = firstReward(c);
          const only = c.allowed_channels.length === 1 ? c.allowed_channels[0] : null;
          return (
            <div className="row" key={c.id}>
              <img className="box" src={boxArt(c.box_art_url)} alt="" />
              <div>
                <div className="row-t">{c.maybe_unlinked ? `${c.game} may need linking` : `Link your ${c.game} account`}</div>
                <div className="row-s">
                  {c.name}
                  {r && <><span className="sep">·</span>“{r.name}” after {dur(r.at)}</>}
                  {only && <><span className="sep">·</span>only on the <b>{only}</b> channel</>}
                  {c.maybe_unlinked && <><span className="sep">·</span>no minutes counted in 10{NB}min of watching</>}
                  <span className="sep">·</span>ends {day(c.ends_at)}
                </div>
                {r && <div className="row-art">{r.all.map((x, i) => <img key={i} src={x.image_url} alt={x.name} />)}</div>}
              </div>
              <div className="row-acts">
                {c.link_url && (
                  <a className="btn strong" href={c.link_url} target="_blank" rel="noopener noreferrer" aria-label={`Link your ${c.game} account (opens the game's site)`}>
                    <Icon name="link" />Link account<Icon name="ext" /></a>
                )}
                {c.maybe_unlinked && (
                  <button className="btn" type="button" aria-label={`Try ${c.name} again`} onClick={async () => {
                    try { await api.post("/mine-now", { campaign_id: c.id }); say(`Trying ${c.name} again`); }
                    catch (e) { sayError(e, "Couldn't start it"); }
                    void refreshState();
                  }}>Mine now</button>
                )}
                <button className="btn quiet" type="button" aria-label={`Ignore ${c.name}`} onClick={() => void ignore(c)}>Ignore</button>
                <button className="btn quiet" type="button" aria-label={`Never mine ${c.game}`} onClick={() => onNever(c.game)}>Never mine</button>
              </div>
            </div>
          );
        })}
        {ignored.length > 0 && toggle(false)}
        {ignoredRows}
      </div>
    </Sec>
  );
}


function Done({ state }: { state: State }) {
  const [open, setOpen] = useState(false);
  if (!state.done.length) return null;
  const rewards = state.done.reduce((n, c) => n + c.drops.reduce((k, d) => k + (d.claimed ? d.rewards.length : 0), 0), 0);
  const games = [...new Set(state.done.map((c) => c.game))];
  return (
    <Sec id="done" title="Done" count={state.done.length} aside="Campaigns still open, everything claimed">
      <div className="list">
        <button className="done-h" type="button" aria-expanded={open} aria-controls="done-body" onClick={() => setOpen(!open)}>
          <span className="done-sum"><span className="chip green">{rewards} {rewards === 1 ? "reward" : "rewards"} claimed</span>
            <span className="hint">{games.join(", ")}</span></span>
          <Icon name="down" className="chev" />
        </button>
        <div className="done-body" id="done-body" hidden={!open}>
          {state.done.map((c) => {
            const got = c.drops.filter((d) => d.claimed).flatMap((d) => d.rewards);
            return (
              <div className="row" key={c.id}>
                <img className="box" src={boxArt(c.box_art_url)} alt="" />
                <div>
                  <div className="row-t">{c.name}</div>
                  <div className="row-s">{c.game}<span className="sep">·</span>all {got.length} claimed<span className="sep">·</span>open until {day(c.ends_at)}</div>
                  <div className="row-art">{got.map((x, i) => <span className="claimed" key={i}><img src={x.image_url} alt={`${x.name}, claimed`} /></span>)}</div>
                  <div className="names" aria-hidden="true">{got.map((x) => x.name).join(", ")}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Sec>
  );
}

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
/** 1st, 2nd, 3rd, 4th, ..., 11th, 12th, 13th, 21st */
export const nth = (n: number) => {
  const t = n % 100;
  const suf = t >= 11 && t <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suf}`;
};

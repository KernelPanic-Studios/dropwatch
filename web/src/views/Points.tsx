import {
  DndContext, DragOverlay, KeyboardSensor, MouseSensor, TouchSensor, closestCenter, useSensor, useSensors, type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS as DndCSS } from "@dnd-kit/utilities";
import { useCallback, useEffect, useState, type HTMLAttributes } from "react";
import { ApiError, api, type PointsChannel, type PointsPage, type Settings, type Suggestions } from "../api/client";
import { useApp } from "../store";
import { clock, day } from "../ui/format";
import { Icon } from "../ui/Icons";
import { AddForm, Bucket, channelNote } from "./Priorities";

const n = (v: number) => v.toLocaleString("en-US");

/** Channel points (asked for 2026-11-08): streamers watched whenever they're live, for their points, apart
 * from drops. Twitch counts two streams at once; one goes to drops while there's a campaign to mine. */
export function PointsView() {
  const { state, say, sayError } = useApp();
  const [page, setPage] = useState<PointsPage | null>(null);
  const [sugg, setSugg] = useState<Suggestions>({ games: [], channels: [] });
  const [claims, setClaims] = useState<boolean | null>(null);
  const [active, setActive] = useState<string | null>(null);
  // as on Priorities: a short mouse move or a press on touch starts a drag, so buttons and scrolling still work
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const load = useCallback(async () => {
    try { setPage(await api.get<PointsPage>("/points")); } catch { /* shown as loading */ }
  }, []);
  // re-read after every miner refresh, so who's live and watched stays current
  useEffect(() => { void load(); }, [load, state?.last_refresh, state?.state]);
  useEffect(() => { api.get<Suggestions>("/suggestions").then(setSugg).catch(() => undefined); }, [state?.last_refresh]);
  useEffect(() => { api.get<Settings>("/settings").then((s) => setClaims(s.claim_points)).catch(() => undefined); }, []);

  const head = <div className="view-h"><h1 id="h-points" className="disp" tabIndex={-1}>Channel points</h1></div>;
  if (!page) return <section className="view" aria-labelledby="h-points">{head}</section>;
  const logins = page.channels.map((c) => c.login);

  async function save(next: string[], message: string) {
    const before = page;
    setPage({ ...page!, channels: next.map((lg) => page!.channels.find((c) => c.login === lg)
      ?? { login: lg, live: false, game: null, viewers: null, last_seen: null, watching: false, watching_since: null, waiting: null, points: 0, chests: 0 }) });
    try {
      setPage(await api.put<PointsPage>("/points/channels", { channels: next }));
      say(message);
    } catch (e) {
      setPage(before);
      say({ title: "Couldn't save the list", detail: e instanceof ApiError ? e.message : undefined, tone: "bad" });
    }
  }
  function move(lg: string, by: number) {
    const L = [...logins];
    const k = L.indexOf(lg);
    const j = k + by;
    if (j < 0 || j >= L.length) return;
    L.splice(k, 1);
    L.splice(j, 0, lg);
    void save(L, `${lg} moved to position ${j + 1} of ${L.length}`).then(() =>
      document.querySelector<HTMLButtonElement>(`.g[data-name="${CSS.escape(lg)}"] [data-act="${by < 0 ? "up" : "down"}"]:not(:disabled)`)?.focus());
  }
  function onDragEnd(e: DragEndEvent) {
    setActive(null);
    const id = String(e.active.id);
    const a = logins.indexOf(id);
    const b = e.over ? logins.indexOf(String(e.over.id)) : -1;
    if (a < 0 || b < 0 || a === b) return;
    void save(arrayMove(logins, a, b), `${id} moved to position ${b + 1} of ${logins.length}`);
  }
  async function toggle(on: boolean) {
    try {
      await api.put<Settings>("/settings", { points_watch: on });
      say(on ? "Watching your streamers for channel points." : "Stopped watching for channel points. The list is kept.");
    } catch (e) { sayError(e, "Couldn't change it"); }
    void load();
  }

  const watching = page.channels.filter((c) => c.watching);
  const known = sugg.channels.filter((c) => !logins.includes(c.login));
  return (
    <section className="view" id="v-points" aria-labelledby="h-points">
      {head}
      <p className="lead">Add the streamers you like and Dropwatch watches them whenever they're live, so their channel points pile
        up even when you can't watch. Twitch counts two streams at a time: while there's a drop to mine one of them goes to drops,
        otherwise both go to this list, top first.</p>
      {page.paused && (
        <div className="banner" role="status"><Icon name="pause" />
          <div><div className="banner-t">Paused</div>
            <div className="banner-b">Nothing is watched while Dropwatch is paused, channel points included. Resume it on Overview.</div></div>
        </div>
      )}
      {claims === false && page.on && (
        <div className="banner" data-tone="note" role="status"><Icon name="coin" />
          <div><div className="banner-t">Bonus chests aren't being opened</div>
            <div className="banner-b">Watching still earns the regular points. Turn on <a href="#settings/points">Also claim channel points</a> to open chests too.</div></div>
        </div>
      )}
      <div className="bucket">
        <div className="opt">
          <div><label htmlFor="p-on">Watch these streamers while they're live</label>
            <div className="d">{page.on
              ? watching.length ? <>Watching {watching.map((c, i) => <span key={c.login}>{i ? " and " : ""}<b>{c.login}</b></span>)} now.</>
                : "Nobody on the list is live right now. Dropwatch checks every 5 minutes."
              : "Off: the list is kept, but nobody is watched for points."}</div></div>
          <input type="checkbox" className="sw" id="p-on" checked={page.on} onChange={(e) => void toggle(e.target.checked)} />
        </div>
      </div>
      {page.points > 0 && (
        <div className="stats">
          <div className="stat"><div className="n">{n(page.points)}</div><div className="l">channel points in the last {page.days} days</div></div>
          <div className="stat"><div className="n">{n(page.chests)}</div><div className="l">{page.chests === 1 ? "bonus chest" : "bonus chests"} opened</div></div>
        </div>
      )}
      <Bucket title="Streamers" count={page.channels.length}
        help="Top to bottom: when more are live than there are free streams, the ones higher up are watched. Points earned here and on drop streams both count.">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={(e) => setActive(String(e.active.id))}
          onDragEnd={onDragEnd} onDragCancel={() => setActive(null)}>
          <div className="zone" id="z-points">
            <SortableContext items={logins} strategy={verticalListSortingStrategy}>
              {page.channels.length ? page.channels.map((c, i) => (
                <SortableRow key={c.login} c={c} i={i} count={page.channels.length} on={page.on} paused={page.paused} days={page.days}
                  onMove={move} onRemove={(lg) => void save(logins.filter((x) => x !== lg), `${lg} removed from Channel points`)} />
              )) : <div className="empty">No streamers yet. Add one below and they'll be watched next time they go live.</div>}
            </SortableContext>
          </div>
          <DragOverlay dropAnimation={{ duration: 180, easing: "cubic-bezier(.2,.8,.2,1)" }}>
            {active && page.channels.some((c) => c.login === active) ? (
              <Row c={page.channels.find((c) => c.login === active)!} i={logins.indexOf(active)} count={logins.length} on={page.on}
                paused={page.paused} days={page.days} onMove={() => undefined} onRemove={() => undefined} lifted />
            ) : null}
          </DragOverlay>
        </DndContext>
        <AddForm to="points" options={known.map((c) => ({ value: c.login, label: channelNote(c) }))} placeholder="Add a streamer" known={sugg.channels.map((c) => c.login)}
          label="Add a streamer to Channel points"
          onAdd={(name) => save([...logins.filter((x) => x !== name.toLowerCase()), name.toLowerCase()], `${name} added to Channel points`)} />
      </Bucket>
    </section>
  );
}

/** "Watching now · Just Chatting · since 14:02", "Live · waiting for a free stream", or when last seen. */
export function pointsStatus(c: PointsChannel, on: boolean, paused: boolean): { text: string; live: boolean } {
  const game = c.game ? ` · ${c.game}` : "";
  if (c.watching) return { text: `Watching now${game}${c.watching_since ? ` · since ${clock(c.watching_since)}` : ""}`, live: true };
  if (c.live && c.waiting === "drops") return { text: `Live${game} · earning on the drops stream`, live: true };
  if (c.live && c.waiting === "full") return { text: `Live${game} · waiting: both streams are taken by streamers higher up`, live: false };
  if (c.live) return { text: `Live${game}${!on ? " · not watched (switched off)" : paused ? " · not watched while paused" : ""}`, live: false };
  if (c.last_seen) return { text: `Offline · last seen ${day(c.last_seen)}${game ? ` on ${c.game}` : ""}`, live: false };
  return { text: "Not seen live yet", live: false };
}

type RowProps = {
  c: PointsChannel; i: number; count: number; on: boolean; paused: boolean; days: number;
  onMove: (lg: string, by: number) => void; onRemove: (lg: string) => void;
};

/** A row that can be dragged to a new place (the up and down buttons do the same from the keyboard). */
function SortableRow(props: RowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: props.c.login });
  return <Row {...props} rootRef={setNodeRef} placeholder={isDragging}
    rootProps={{ ...attributes, ...listeners, style: { transform: DndCSS.Translate.toString(transform), transition } }} />;
}

function Row({ c, i, count, on, paused, days, onMove, onRemove, rootRef, rootProps, placeholder, lifted }: RowProps & {
  rootRef?: (el: HTMLElement | null) => void; rootProps?: HTMLAttributes<HTMLDivElement>; placeholder?: boolean; lifted?: boolean;
}) {
  const st = pointsStatus(c, on, paused);
  const earned = c.points > 0 ? `${n(c.points)} points${c.chests ? ` · ${c.chests} ${c.chests === 1 ? "chest" : "chests"}` : ""} in ${days} days` : "";
  return (
    <div {...rootProps} ref={rootRef} className={`g fav${placeholder ? " placeholder" : ""}${lifted ? " lifted" : ""}`} data-name={c.login}>
      <span className="rank">{i + 1}</span><span className="handle" aria-hidden="true"><Icon name="grip" /></span>
      <span className="avatar" aria-hidden="true">{c.login.charAt(0)}</span>
      <div style={{ minWidth: 0 }}><div className="g-t">{c.login}</div>
        <div className="g-s">{st.live ? <span className="on">{st.text}</span> : st.text}{earned && <> · {earned}</>}</div></div>
      <div className="g-act">
        <button className="ib" type="button" data-act="up" aria-label={`Move ${c.login} up`} disabled={i === 0} onClick={() => onMove(c.login, -1)}><Icon name="up" /></button>
        <button className="ib" type="button" data-act="down" aria-label={`Move ${c.login} down`} disabled={i === count - 1} onClick={() => onMove(c.login, 1)}><Icon name="down" /></button>
        <button className="btn quiet" type="button" data-act="remove" aria-label={`Remove ${c.login} from Channel points`} onClick={() => onRemove(c.login)}>Remove</button>
      </div>
    </div>
  );
}

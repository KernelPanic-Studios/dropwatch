import {
  DndContext, DragOverlay, KeyboardSensor, MouseSensor, TouchSensor, closestCenter, useDroppable, useSensor, useSensors,
  type DragEndEvent, type DragOverEvent, type DragStartEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS as DndCSS } from "@dnd-kit/utilities";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Campaign, type ChannelSuggestion, type Lists, type State, type Suggestions } from "../api/client";
import { useLists } from "../lists";
import { useApp } from "../store";
import { boxArt, day, dur } from "../ui/format";
import { Icon } from "../ui/Icons";

type Zone = "priority" | "fav" | "never";
const KEY: Record<Zone, keyof Lists> = { priority: "priority", fav: "favourites", never: "never" };
const NAME: Record<Zone, string> = { priority: "Priority", fav: "favourite channels", never: "Never" };
const EMPTY: Record<Zone, string> = {
  never: "Nothing blocked. Add a game below to stop it being mined.",
  priority: "No priority games. Everything is mined most urgent first.",
  fav: "No favourites. For each campaign, any live channel with drops on will do.",
};

/** Priorities (approved mockup): Priority (ordered), Favourite channels (ordered), Never. */
export function PrioritiesView() {
  const { state, say } = useApp();
  const { lists, save } = useLists();
  const [sugg, setSugg] = useState<Suggestions>({ games: [], channels: [] });
  const [focus, setFocus] = useState<[string, string] | null>(null);
  const [draft, setDraft] = useState<Lists | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 4 } }), // buttons in the row still click
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 6 } }), // a press, so phones can scroll
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  // re-read after every miner refresh so "Live now" stays current
  useEffect(() => { api.get<Suggestions>("/suggestions").then(setSugg).catch(() => undefined); }, [state?.last_refresh]);
  useEffect(() => {
    if (!focus) return;
    const [name, act] = focus;
    const row = document.querySelector<HTMLElement>(`.g[data-name="${CSS.escape(name)}"]`);
    let el = row?.querySelector<HTMLButtonElement>(`[data-act="${act}"]`) ?? null;
    if (!el || el.disabled) el = row?.querySelector<HTMLButtonElement>("button:not(:disabled)") ?? null;
    (el ?? document.getElementById("h-priorities"))?.focus();
    setFocus(null);
  }, [focus, lists]);

  if (!lists) {
    return <section className="view" aria-labelledby="h-priorities"><div className="view-h"><h1 id="h-priorities" className="disp" tabIndex={-1}>Priorities</h1></div></section>;
  }

  const zoneOf = (name: string): Zone | "pool" =>
    lists.favourites.includes(name) ? "fav" : lists.never.includes(name) ? "never" : lists.priority.includes(name) ? "priority" : "pool";

  /** The mockup's move(): games move between Priority / Never / nowhere; channels only in or out of favourites. */
  function moved(name: string, to: Zone | "pool", index?: number): Lists {
    const next: Lists = { priority: [...lists!.priority], never: [...lists!.never], favourites: [...lists!.favourites] };
    if (to === "fav" || zoneOf(name) === "fav") {
      next.favourites = next.favourites.filter((n) => n !== name);
      if (to !== "fav") return next;
    } else {
      next.priority = next.priority.filter((n) => n !== name);
      next.never = next.never.filter((n) => n !== name);
    }
    if (to === "pool") return next;
    const list = next[KEY[to]];
    if (index === undefined || index > list.length) list.push(name);
    else list.splice(index, 0, name);
    return next;
  }

  async function commit(next: Lists, message: string, f?: [string, string]) {
    const err = await save(next);
    say(err ? { title: "Couldn't save the lists", detail: err, tone: "bad" } : message);
    if (f) setFocus(f);
    else document.getElementById("h-priorities")?.focus();
  }

  function onAct(name: string, act: string) {
    const z = zoneOf(name);
    if (act === "up" || act === "down") {
      if (z === "pool") return;
      const L = [...lists![KEY[z]]];
      const k = L.indexOf(name);
      const j = act === "up" ? k - 1 : k + 1;
      if (j < 0 || j >= L.length) return;
      L.splice(k, 1);
      L.splice(j, 0, name);
      void commit({ ...lists!, [KEY[z]]: L }, `${name} moved to position ${j + 1} of ${L.length}`, [name, act]);
    } else if (act === "never") void commit(moved(name, "never"), `${name} moved to Never`, [name, "remove"]);
    else if (act === "priority") void commit(moved(name, "priority"), `${name} added to Priority at position ${lists!.priority.filter((n) => n !== name).length + 1}`, [name, "up"]);
    else if (act === "remove") {
      void commit(moved(name, "pool"), `${name} removed from ${z === "pool" ? "the list" : NAME[z]}${z === "fav" ? "." : ". It will be mined by urgency."}`);
    }
  }

  /* Drag to reorder (dnd-kit): the row lifts and follows the pointer while the others slide apart; games can
   * also move between Priority and Never; the save happens once, on drop. */
  const shown = draft ?? lists;
  const containerOf = (id: string, L: Lists): Zone | null =>
    (["priority", "never", "fav"] as Zone[]).find((z) => z === id || L[KEY[z]].includes(id)) ?? null;
  function onDragStart(e: DragStartEvent) {
    setActive(String(e.active.id));
    setDraft({ priority: [...lists!.priority], never: [...lists!.never], favourites: [...lists!.favourites] });
  }
  function onDragOver(e: DragOverEvent) {
    if (!e.over || !draft) return;
    const id = String(e.active.id);
    const from = containerOf(id, draft);
    const to = containerOf(String(e.over.id), draft);
    if (!from || !to || from === to || (from === "fav") !== (to === "fav")) return; // channels and games don't mix
    const target = draft[KEY[to]];
    const overIdx = target.indexOf(String(e.over.id));
    const next = { ...draft, [KEY[from]]: draft[KEY[from]].filter((n) => n !== id) } as Lists;
    const list = [...target];
    list.splice(overIdx < 0 ? list.length : overIdx, 0, id);
    setDraft({ ...next, [KEY[to]]: list });
  }
  function onDragEnd(e: DragEndEvent) {
    const id = String(e.active.id);
    let next = draft;
    setActive(null);
    setDraft(null);
    if (!next || !e.over) return;
    const z = containerOf(id, next);
    if (z) {
      const L = next[KEY[z]];
      const a = L.indexOf(id);
      const b = L.indexOf(String(e.over.id));
      if (b >= 0 && a !== b) next = { ...next, [KEY[z]]: arrayMove(L, a, b) };
    }
    const same = (["priority", "never", "favourites"] as const).every((k) => next![k].join("\n") === lists![k].join("\n"));
    if (same || !z) return;
    const pos = next[KEY[z]].indexOf(id) + 1;
    void commit(next, z === "never" ? `${id} moved to Never` : `${id} moved to position ${pos} of ${next[KEY[z]].length} in ${z === "fav" ? "favourite channels" : "Priority"}`);
  }

  const info = gameInfo(state);
  const chan = new Map(sugg.channels.map((c) => [c.login, c]));
  const pool = sugg.games.filter((g) => !lists.priority.includes(g) && !lists.never.includes(g));
  const gameOpts = pool.map((g) => ({ value: g }));
  const chanOpts = sugg.channels.filter((c) => !lists.favourites.includes(c.login))
    .map((c) => ({ value: c.login, label: channelNote(c) }));

  const zone = (z: Zone) => {
    const list = shown[KEY[z]];
    return (
      <DropZone id={z}>
        <SortableContext items={list} strategy={verticalListSortingStrategy}>
          {list.length ? list.map((n, i) => (
            <SortableRow key={n} name={n} zone={z} i={i} n={list.length} info={info} ch={chan.get(n)}
              onAct={onAct} />
          )) : <div className="empty">{EMPTY[z]}</div>}
        </SortableContext>
      </DropZone>
    );
  };
  const activeZone = active ? containerOf(active, shown) : null;

  return (
    <section className="view" id="v-priorities" aria-labelledby="h-priorities">
      <div className="view-h"><h1 id="h-priorities" className="disp" tabIndex={-1}>Priorities</h1></div>
      <p className="lead">Every game with a drop campaign gets mined. Games in Priority go first, in your order. Games not listed here are mined after them, most urgent first. Overview shows the full order under Up next.</p>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={onDragStart} onDragOver={onDragOver}
        onDragEnd={onDragEnd} onDragCancel={() => { setActive(null); setDraft(null); }}>
      <Bucket title="Priority" count={shown.priority.length} help="Mined first, top to bottom.">
        {zone("priority")}
        <AddForm to="priority" options={gameOpts} placeholder="Add a game" known={sugg.games} label="Add a game to Priority"
          onAdd={(name) => commit(moved(name, "priority"), `${name} added to Priority`)} />
      </Bucket>
      <Bucket title="Favourite channels" count={shown.favourites.length}
        help="When a campaign can be mined on several live channels, these get watched first, top to bottom. Your game order above still decides which campaign.">
        {zone("fav")}
        <AddForm to="fav" options={chanOpts} placeholder="Add a channel" known={sugg.channels.map((c) => c.login)} label="Add a favourite channel"
          onAdd={(name) => commit(moved(name.toLowerCase(), "fav"), `${name} added to favourite channels`)} />
      </Bucket>
      <Bucket title="Never" count={shown.never.length} help="Never mined, even when nothing else is live.">
        {zone("never")}
        <AddForm to="never" options={gameOpts} placeholder="Add a game" known={sugg.games} label="Add a game to Never"
          onAdd={(name) => commit(moved(name, "never"), `${name} added to Never`)} />
      </Bucket>
      <DragOverlay dropAnimation={{ duration: 180, easing: "cubic-bezier(.2,.8,.2,1)" }}>
        {active && activeZone ? (
          <RowBody name={active} zone={activeZone} i={shown[KEY[activeZone]].indexOf(active)} n={shown[KEY[activeZone]].length}
            info={info} ch={chan.get(active)} onAct={() => undefined} lifted />
        ) : null}
      </DragOverlay>
      </DndContext>
    </section>
  );
}

export function Bucket({ title, count, help, children }: { title: string; count: number; help: string; children: React.ReactNode }) {
  return (
    <div className="bucket">
      <div className="bucket-h"><h2>{title}</h2><span className="count">{count}</span><p>{help}</p></div>
      {children}
    </div>
  );
}

type Info = Map<string, { text: string; warn?: boolean; art?: string }>;

/** What each game is doing right now, for the row subtitles (as in the mockup). */
function gameInfo(state: State | null): Info {
  const m: Info = new Map();
  if (!state) return m;
  const put = (c: Campaign, text: string, warn = false) => { if (!m.has(c.game)) m.set(c.game, { text, warn, art: boxArt(c.box_art_url) }); };
  if (state.current) put(state.current.campaign, `Mining now · ${dur(state.current.campaign.minutes_needed)} to go · ends ${day(state.current.campaign.ends_at)}`);
  for (const c of state.needs_you) put(c, `${c.maybe_unlinked ? "May need account link" : "Needs account link"} · ends ${day(c.ends_at)}`, true);
  for (const c of state.up_next) put(c, `${dur(c.minutes_needed)} to go · ends ${day(c.ends_at)}`);
  for (const c of state.done) {
    const n = c.drops.reduce((k, d) => k + d.rewards.length, 0);
    put(c, `All ${n} ${n === 1 ? "reward" : "rewards"} claimed`);
  }
  for (const c of state.never ?? []) put(c, `Campaign running · ends ${day(c.ends_at)}`);
  return m;
}

function DropZone({ id, children }: { id: Zone; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return <div ref={setNodeRef} className={`zone${isOver ? " over" : ""}`} data-zone={id} id={`z-${id}`}>{children}</div>;
}

type RowProps = { name: string; zone: Zone; i: number; n: number; info: Info; ch?: ChannelSuggestion; onAct: (name: string, act: string) => void };

/** "Live now · Palia", "Offline · last seen Tue 13 Oct on Palia", or "Not seen live yet". */
export function channelNote(c: ChannelSuggestion | undefined): string {
  if (!c) return "Not seen live yet";
  if (c.live) return `Live now${c.game ? ` · ${c.game}` : ""}`;
  if (c.last_seen) return `Offline · last seen ${day(c.last_seen)}${c.game ? ` on ${c.game}` : ""}`;
  return "Not seen live yet";
}

function SortableRow(props: RowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: props.name });
  return (
    <RowBody {...props} rootRef={setNodeRef} placeholder={isDragging}
      rootProps={{ ...attributes, ...listeners, style: { transform: DndCSS.Translate.toString(transform), transition } }} />
  );
}

function RowBody({ name, zone, i, n, info, ch, onAct, rootRef, rootProps, placeholder, lifted }: RowProps & {
  rootRef?: (el: HTMLElement | null) => void; rootProps?: React.HTMLAttributes<HTMLDivElement>; placeholder?: boolean; lifted?: boolean;
}) {
  const btn = (act: string, label: string, content: React.ReactNode, cls = "ib", disabled = false) => (
    <button className={cls} type="button" data-act={act} aria-label={label} disabled={disabled} onClick={() => onAct(name, act)}>{content}</button>
  );
  const common = {
    ...rootProps, ref: rootRef,
    className: `g ${zone}${placeholder ? " placeholder" : ""}${lifted ? " lifted" : ""}`, "data-name": name,
  };
  if (zone === "fav") {
    return (
      <div {...common}>
        <span className="rank">{i + 1}</span><span className="handle" aria-hidden="true"><Icon name="grip" /></span>
        <span className="avatar" aria-hidden="true">{name.charAt(0)}</span>
        <div style={{ minWidth: 0 }}><div className="g-t">{name}</div>
          <div className="g-s">{ch?.live ? <span className="on">{channelNote(ch)}</span> : channelNote(ch)}</div></div>
        <div className="g-act">
          {btn("up", `Move ${name} up`, <Icon name="up" />, "ib", i === 0)}
          {btn("down", `Move ${name} down`, <Icon name="down" />, "ib", i === n - 1)}
          {btn("remove", `Remove ${name} from favourite channels`, "Remove", "btn quiet")}
        </div>
      </div>
    );
  }
  const inf = info.get(name);
  return (
    <div {...common}>
      <span className="rank">{zone === "priority" ? i + 1 : ""}</span><span className="handle" aria-hidden="true"><Icon name="grip" /></span>
      {inf?.art ? <img className="box" src={inf.art} alt="" /> : <span className="box ph" style={{ width: 36 }} aria-hidden="true" />}
      <div style={{ minWidth: 0 }}><div className="g-t">{name}</div>
        <div className={`g-s${inf?.warn ? " warn" : ""}`}>{inf?.text ?? "No campaign right now"}</div></div>
      <div className="g-act">
        {zone === "priority" ? <>
          {btn("up", `Move ${name} up`, <Icon name="up" />, "ib", i === 0)}
          {btn("down", `Move ${name} down`, <Icon name="down" />, "ib", i === n - 1)}
          {btn("never", `Never mine ${name}`, "Never mine", "btn quiet")}
          {btn("remove", `Remove ${name} from Priority`, "Remove", "btn quiet")}
        </> : <>
          {btn("priority", `Move ${name} to Priority`, "Prioritise", "btn quiet")}
          {btn("remove", `Allow ${name} again`, "Allow again", "btn quiet")}
        </>}
      </div>
    </div>
  );
}

export const MIN_TYPED = 3;  // suggestions start after this many letters
const MAX_SUGGESTED = 8;

/** The add box's suggestions: none until MIN_TYPED letters are typed, then the best few matches. A whole
 * match first, then names starting with it, then a word inside the name starting with it ("speed" finds
 * "sam_speedruns"), then anywhere in it; shorter names first within each. */
export function bestMatches<T extends { value: string }>(options: T[], typed: string, max = MAX_SUGGESTED): T[] {
  const q = typed.trim().toLowerCase();
  if (q.length < MIN_TYPED) return [];
  const rank = (name: string) => {
    const n = name.toLowerCase();
    if (n === q) return 0;
    if (n.startsWith(q)) return 1;
    if (n.split(/[\s_\-:.]+/).some((w) => w.startsWith(q))) return 2;
    return n.includes(q) ? 3 : -1;
  };
  return options.map((o) => [rank(o.value), o] as const).filter(([r]) => r >= 0)
    .sort(([ra, a], [rb, b]) => ra - rb || a.value.length - b.value.length || a.value.localeCompare(b.value))
    .slice(0, max).map(([, o]) => o);
}

/** What was typed in a channel box, as a Twitch login: a name ("@Quibble_Bibble") or a channel link
 * ("https://www.twitch.tv/quibble_bibble/videos?x=1", "m.twitch.tv/…"). Null when it can't be one. */
export function channelLogin(text: string): string | null {
  let t = text.trim().replace(/^@/, "");
  const link = t.match(/^(?:https?:\/\/)?(?:www\.|m\.|go\.)?twitch\.tv\/([^/?#\s]+)/i);
  if (link) t = link[1]!;
  return /^[A-Za-z0-9_]{1,25}$/.test(t) ? t.toLowerCase() : null;
}

type Lookup = { login: string; found: boolean; display_name?: string | null; live?: boolean; game?: string | null };
type Check = { login: string } & ({ status: "checking" } | { status: "done"; got: Lookup } | { status: "error" } | { status: "bad" });

export function AddForm({ to, options, placeholder, known, label, onAdd }: {
  to: Zone | "points"; options: { value: string; label?: string }[]; placeholder: string; known: string[]; label: string; onAdd: (name: string) => Promise<void> | void;
}) {
  const channels = to === "fav" || to === "points";
  const [v, setV] = useState("");
  const [unknown, setUnknown] = useState<string | null>(null);
  const [check, setCheck] = useState<Check | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const asking = useRef<{ login: string; p: Promise<Check> } | null>(null);  // blur and Add share one request

  /** Channel boxes: ask Twitch whether the name exists (on blur, and before adding a name not seen yet). */
  async function lookUp(raw: string): Promise<Check | null> {
    if (!raw.trim()) { setCheck(null); return null; }
    const login = channelLogin(raw);
    if (!login) { const c: Check = { login: raw.trim(), status: "bad" }; setCheck(c); return c; }
    if (login !== raw.trim()) setV(login);  // a pasted link becomes the name it points at
    if (asking.current?.login === login) return asking.current.p;
    setCheck({ login, status: "checking" });
    const p = api.get<Lookup>(`/channels/lookup?login=${encodeURIComponent(login)}`)
      .then((got): Check => ({ login, status: "done", got }), (): Check => ({ login, status: "error" }));
    asking.current = { login, p };
    const c = await p;
    if (c.status === "error" && asking.current?.p === p) asking.current = null;  // try again next time
    setCheck((now) => (now && now.login === login ? c : now));
    return c;
  }
  async function add(name: string) {
    setV(""); setUnknown(null); setCheck(null); asking.current = null;
    await onAdd(name);
    input.current?.focus();
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    const val = v.trim();
    if (!val) return;
    const name = channels ? channelLogin(val) : val;
    const match = name && known.find((n) => n.toLowerCase() === name.toLowerCase());
    if (match) { await add(match); return; }
    if (!channels) { setUnknown(val); return; }
    const c = await lookUp(val);
    if (c?.status === "done" && c.got.found) await add(c.got.login);
    else if (c?.status === "error") setUnknown(c.login);  // couldn't ask Twitch: the old question
  }
  const note = channels && check && (
    check.status === "checking" ? <div className="add-note">Checking Twitch for <b>{check.login}</b>…</div>
      : check.status === "bad" ? <div className="add-note warn">That isn't a Twitch name or channel link.</div>
      : check.status === "done" && check.got.found ? (
        <div className="add-note ok"><Icon name="check" /><span><b>{check.got.display_name ?? check.got.login}</b> is on Twitch
          {check.got.live ? <> · <span className="on">Live now{check.got.game ? ` · ${check.got.game}` : ""}</span></> : " · Offline"}</span></div>)
      : check.status === "done" ? <div className="add-note warn">Twitch has no channel called <b>{check.login}</b>. Check the spelling.</div>
      : null);
  return (
    <form className="add" data-to={to} noValidate onSubmit={submit}>
      <datalist id={`opts-${to}`}>
        {bestMatches(options, v).map((o) => <option key={o.value} value={o.value} label={o.label} />)}
      </datalist>
      <div className="add-row">
        <input ref={input} id={`add-${to}`} type="text" list={`opts-${to}`} placeholder={placeholder} aria-label={label} autoComplete="off"
          value={v} onChange={(e) => { setV(e.target.value); if (check) setCheck(null); setUnknown(null); }}
          onBlur={channels ? () => void lookUp(v) : undefined} />
        <button className="btn" type="submit">Add</button>
      </div>
      <div className="add-live" aria-live="polite">{note}</div>
      {unknown && (
        <div className="confirm">
          <span>{channels
            ? <>Couldn't check <b>{unknown}</b> with Twitch just now. Check the spelling, or add it anyway.</>
            : <>No game called <b>{unknown}</b> has a campaign right now. Check the spelling, or add it so it's ready when one starts.</>}</span>
          <span className="acts">
            <button className="btn" type="button" onClick={() => void add(unknown)}>Add anyway</button>
            <button className="btn quiet" type="button" onClick={() => { setUnknown(null); input.current?.focus(); }}>Cancel</button>
          </span>
        </div>
      )}
    </form>
  );
}

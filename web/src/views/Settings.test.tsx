import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, Toasts } from "../store";
import { mockApi } from "../test/fetch";
import { state } from "../test/fixtures";
import { SettingsView } from "./Settings";

const SETTINGS = { mine_badges: false, claim_points: true, notify_target: "", notify_claimed: true, notify_needs_you: true, notify_signin: true };
afterEach(() => vi.unstubAllGlobals());

/** Settings shows one section at a time; the hash picks it (#settings/<section>). */
function setup(section: string, extra: Record<string, unknown> = {}) {
  location.hash = `#settings/${section}`;
  const calls = mockApi({ "GET /api/state": state(), "GET /api/settings": SETTINGS, ...extra });
  render(<AppProvider initialMe={{ authenticated: true, setup_required: false }}><SettingsView /><Toasts /></AppProvider>);
  return calls;
}

test("Twitch sign-out asks first; Stay signed in returns focus and does nothing", async () => {
  const calls = setup("account", { "POST /api/twitch/signout": undefined });
  const u = userEvent.setup();
  const btn = await screen.findByRole("button", { name: "Sign out" , description: "" });
  await u.click(screen.getAllByRole("button", { name: "Sign out" })[0]!);
  const stay = screen.getByRole("button", { name: "Stay signed in" });
  expect(stay).toHaveFocus();
  await u.click(stay);
  expect(document.querySelector(".confirm")).toBeNull(); // the sign-in alert shares this wording, so look at the box
  expect(calls.some((c) => c.path === "/api/twitch/signout")).toBe(false);
  expect(btn).toBeInTheDocument();
  await u.click(screen.getAllByRole("button", { name: "Sign out" })[0]!);
  const confirmBox = document.querySelector(".confirm")!;
  await u.click(confirmBox.querySelector("button.btn:not(.quiet)")!);
  await waitFor(() => expect(calls.some((c) => c.path === "/api/twitch/signout")).toBe(true));
});

test("the badges switch saves straight away", async () => {
  const calls = setup("mining", { "PUT /api/settings": { ...SETTINGS, mine_badges: true } });
  const sw = await screen.findByRole("checkbox", { name: "Also mine badge and emote campaigns" });
  await waitFor(() => expect(sw).toBeEnabled());
  await userEvent.click(sw);
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ mine_badges: true }));
  expect(sw).toBeChecked();
});

test("the old single-URL notification design is gone (replaced 2026-10-10)", async () => {
  setup("notifications");
  await screen.findByRole("heading", { name: "Alerts" });
  expect(screen.queryByText(/An ntfy topic or a Discord webhook URL/)).not.toBeInTheDocument();
});

test("Also claim channel points is on and saves when switched", async () => {
  const calls = setup("points", { "PUT /api/settings": (b: object) => ({ ...SETTINGS, ...b }) });
  const u = userEvent.setup();
  const sw = await screen.findByRole("checkbox", { name: "Also claim channel points" });
  await waitFor(() => expect(sw).toBeChecked());
  await u.click(sw);
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ claim_points: false }));
});

const ABOUT = { version: "0.1.0", commit: "main@abc1234", started_at: "2026-10-10T20:30:00Z",
  campaigns_at: "2026-10-10T21:30:00Z", server_tz: "UTC" };

test("About names the version and commit that is running", async () => {
  setup("about", { "GET /api/about": ABOUT });
  const pane = (await screen.findByRole("heading", { name: "About" })).closest(".set") as HTMLElement;
  expect(await within(pane).findByText("main@abc1234")).toBeInTheDocument();
  expect(within(pane).getByText("0.1.0")).toBeInTheDocument();
  expect(within(pane).getByText(/Running since/)).toBeInTheDocument();
});

test("the weekly summary's time zone defaults to the server's and saves a chosen one", async () => {
  const calls = setup("notifications", { "GET /api/about": ABOUT, "PUT /api/settings": { ...SETTINGS, notify_weekly_tz: "America/New_York" } });
  const zone = await screen.findByRole("combobox", { name: "Time zone" });
  await screen.findByRole("option", { name: "Server time (UTC)" });
  await waitFor(() => expect(zone).toBeEnabled());
  expect(zone).toHaveValue("");
  await userEvent.selectOptions(zone, "America/New_York");
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ notify_weekly_tz: "America/New_York" }));
});

test("Backup: save links to the file, with secrets only when ticked", async () => {
  setup("backup", { "GET /api/about": ABOUT });
  const save = await screen.findByRole("link", { name: "Save a backup" });
  expect(save).toHaveAttribute("href", "api/backup");
  expect(save).toHaveAttribute("download");
  await userEvent.click(screen.getByRole("checkbox", { name: /Include notification secrets/ }));
  expect(save).toHaveAttribute("href", "api/backup?secrets=true");
});

test("Backup: restore asks first, then replaces and says what it skipped", async () => {
  const backup = { dropwatch_backup: 1, made_at: "2026-10-09T12:00:00Z", lists: {}, pins: [], settings: {}, notify_channels: {} };
  const calls = setup("backup", { "GET /api/about": ABOUT, "POST /api/restore": { skipped: ["channel matrix"] } });
  const u = userEvent.setup();
  const input = await screen.findByLabelText("Restore from a backup");
  await u.upload(input, new File([JSON.stringify(backup)], "dropwatch-backup-2026-10-09.json", { type: "application/json" }));
  expect(await screen.findByText(/Replace your lists, settings and notification channels/)).toBeInTheDocument();
  expect(calls.some((c) => c.path === "/api/restore")).toBe(false);
  await u.click(screen.getByRole("button", { name: "Replace" }));
  await waitFor(() => expect(calls.find((c) => c.path === "/api/restore")?.body).toEqual(backup));
  expect(await screen.findByText(/Backup restored.*channel matrix/, { selector: ".d" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: /Backup restored/ })).toHaveClass("ok");
});

test("Backup: a file that isn't JSON is refused before anything is sent", async () => {
  const calls = setup("backup", { "GET /api/about": ABOUT });
  const input = await screen.findByLabelText("Restore from a backup");
  await userEvent.upload(input, new File(["not json"], "x.json", { type: "application/json" }));
  expect(await screen.findByText("That file isn't a Dropwatch backup.", { selector: ".d" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "That file isn't a Dropwatch backup." })).toHaveClass("bad"); // review fix: was a green tick
  expect(calls.some((c) => c.path === "/api/restore")).toBe(false);
});

test("how often campaigns are re-read is chosen in Mining and saves straight away", async () => {
  const calls = setup("mining", { "PUT /api/settings": { ...SETTINGS, campaigns_every_minutes: 15 } });
  const sel = await screen.findByRole("combobox", { name: "Check Twitch for campaign changes" });
  await waitFor(() => expect(sel).toBeEnabled());
  expect([...(sel as HTMLSelectElement).options].map((o) => o.text)).toEqual(["Every 15 min", "Every 30 min", "Every hour", "Every 2 hours", "Every 4 hours"]);
  await userEvent.selectOptions(sel, "15");
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ campaigns_every_minutes: 15 }));
});

test("the watch-streak switch saves straight away", async () => {
  const calls = setup("points", { "GET /api/settings": { ...SETTINGS, points_watch_streak: true }, "PUT /api/settings": { ...SETTINGS, points_watch_streak: false } });
  const sw = await screen.findByRole("checkbox", { name: "Collect watch-streak bonuses on favourite channels" });
  await waitFor(() => expect(sw).toBeEnabled());
  await userEvent.click(sw);
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ points_watch_streak: false }));
});

/* The reorganisation (2026-10-11, settings-mockup.html package 2): a section list with summaries, one open. */
test("one section shows at a time: the hash picks it, Mining by default and for anything unknown", async () => {
  setup("");
  expect(await screen.findByRole("heading", { name: "Mining" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /^Mining/ })).toHaveAttribute("aria-current", "page");
  expect(screen.queryByRole("heading", { name: "Backup" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: /^Backup/ }));
  expect(await screen.findByRole("heading", { name: "Backup" })).toBeInTheDocument();
  expect(location.hash).toBe("#settings/backup");
  expect(screen.queryByRole("heading", { name: "Mining" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /^Backup/ })).toHaveAttribute("aria-current", "page");
  location.hash = "#settings/nope";
  expect(await screen.findByRole("heading", { name: "Mining" })).toBeInTheDocument();
});

test("each section in the list says what's set", async () => {
  const sessions = { sessions: Array.from({ length: 6 }, (_, i) => ({ id: `s${i}`, device: `B${i}`, created_at: "2026-10-10T20:00:00Z",
    last_seen_at: null, current: i === 0 })) };
  setup("about", {
    "GET /api/settings": { mine_badges: true, campaigns_every_minutes: 60, claim_points: true, points_watch_streak: false,
      notify_signin: true, notify_unreachable: true, notify_not_earning: true, notify_claim_failed: true, notify_stopped: true,
      notify_needs_you: false, notify_weekly: true, notify_weekly_day: 6, notify_weekly_hour: 21 },
    "GET /api/notify/channels": { channels: [{ type: "discord", name: "Discord", configured: true, summary: "", hint: "", fields: [] }], available: [] },
    "GET /api/sessions": sessions, "GET /api/about": ABOUT,
  });
  const link = (name: RegExp) => screen.getByRole("link", { name });
  await waitFor(() => expect(link(/^Notifications/)).toHaveTextContent("5 of 6 alerts · weekly Sun 21:00 UTC · Discord"));
  expect(link(/^Mining/)).toHaveTextContent("Badges on · every hour");
  expect(link(/^Channel points/)).toHaveTextContent("Chests on · streaks off");
  await waitFor(() => expect(link(/^Account/)).toHaveTextContent("kernelpanicattack · 6 browsers"));
  expect(link(/^About/)).toHaveTextContent("0.1.0");
});

test("with channel points off the list says Off, and no channel set says so", async () => {
  setup("mining", { "GET /api/settings": { ...SETTINGS, claim_points: false, notify_weekly: false },
    "GET /api/notify/channels": { channels: [], available: [] } });
  await waitFor(() => expect(screen.getByRole("link", { name: /^Channel points/ })).toHaveTextContent(/Channel pointsOff$/));
  await waitFor(() => expect(screen.getByRole("link", { name: /^Notifications/ })).toHaveTextContent(/alerts · nowhere to send them$/));
});

/* Polish (2026-10-12): the weekly time names its zone, and the section list keeps its height while loading. */
test("the weekly summary time says which zone it's in", async () => {
  setup("about", {
    "GET /api/settings": { ...SETTINGS, notify_weekly: true, notify_weekly_day: 6, notify_weekly_hour: 21,
      notify_weekly_tz: "America/New_York" },
    "GET /api/notify/channels": { channels: [], available: [] }, "GET /api/about": ABOUT,
  });
  await waitFor(() => expect(screen.getByRole("link", { name: /^Notifications/ })).toHaveTextContent(/weekly Sun 21:00 E[SD]T/));
});

test("every section already has its summary line before the data arrives", () => {
  setup("mining");
  const links = screen.getAllByRole("link");
  expect(links).toHaveLength(8);
  for (const l of links) expect(l.querySelector("small")).not.toBeNull();
});

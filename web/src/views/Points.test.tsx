import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import { mockApi } from "../test/fetch";
import { state } from "../test/fixtures";
import { PointsNote } from "./Overview";
import { PointsView } from "./Points";
import { channelLogin } from "./Priorities";

const ME = { authenticated: true, setup_required: false };
function Said() {
  return <div data-testid="said">{useApp().announcement}</div>;
}
afterEach(() => vi.unstubAllGlobals());

const row = (login: string, over: Record<string, unknown> = {}) => ({
  login, live: false, game: null, viewers: null, last_seen: null, watching: false, watching_since: null, waiting: null,
  points: 0, chests: 0, ...over,
});
const PAGE = {
  on: true, paused: false, days: 30, points: 1250, chests: 3, channels: [
    row("alice", { live: true, game: "Just Chatting", viewers: 900, watching: true, watching_since: "2026-11-08T14:02:00Z", points: 1200, chests: 3 }),
    row("bob", { live: true, game: "Minecraft", waiting: "full" }),
    row("carol", { last_seen: "2026-11-01T20:00:00Z", game: "Palia", points: 50 }),
  ],
};

const QUIBBLE = { login: "quibble_bibble", found: true, display_name: "Quibble_Bibble", live: false, game: "Palia" };

function setup(page: unknown = PAGE, put?: (b: unknown) => unknown, claims = true, lookup: unknown = QUIBBLE) {
  const calls = mockApi({
    "GET /api/state": state(), "GET /api/points": page, "GET /api/settings": { claim_points: claims },
    "GET /api/suggestions": { games: [], channels: [{ login: "dave", live: true, game: "Palia", last_seen: null }] },
    "PUT /api/points/channels": put ?? ((b: { channels: string[] }) => ({ ...PAGE, channels: b.channels.map((lg) => PAGE.channels.find((c) => c.login === lg) ?? row(lg)) })),
    "PUT /api/settings": { claim_points: claims, points_watch: false },
    "GET /api/channels/lookup": lookup,
  });
  render(<AppProvider initialMe={ME}><PointsView /><Said /></AppProvider>);
  return calls;
}

test("lists each streamer with what it's doing and what it earned", async () => {
  setup();
  expect((await screen.findByText(/Watching now · Just Chatting/)).closest(".g-s")).toHaveTextContent("1,200 points · 3 chests in 30 days");
  expect(screen.getByText(/waiting: both streams are taken/)).toBeInTheDocument();
  expect(screen.getByText(/Offline · last seen/)).toHaveTextContent("50 points in 30 days");
  expect(screen.getByText("1,250")).toBeInTheDocument();
});

test("adding a streamer saves the list with it at the bottom", async () => {
  const calls = setup();
  const u = userEvent.setup();
  await u.type(await screen.findByRole("combobox", { name: "Add a streamer to Channel points" }), "Dave");
  await u.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ channels: ["alice", "bob", "carol", "dave"] }));
  await waitFor(() => expect(screen.getByTestId("said")).toHaveTextContent("dave added to Channel points"));
});

test("moving and removing save the new order", async () => {
  const calls = setup();
  const u = userEvent.setup();
  await u.click(await screen.findByRole("button", { name: "Move bob up" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "PUT").at(-1)?.body).toEqual({ channels: ["bob", "alice", "carol"] }));
  await u.click(screen.getByRole("button", { name: "Remove carol from Channel points" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "PUT").at(-1)?.body).toEqual({ channels: ["bob", "alice"] }));
});

test("the switch turns points watching off, and chests being off is pointed out", async () => {
  const calls = setup(PAGE, undefined, false);
  const u = userEvent.setup();
  expect(await screen.findByText("Bonus chests aren't being opened")).toBeInTheDocument();
  await u.click(screen.getByRole("checkbox", { name: "Watch these streamers while they're live" }));
  await waitFor(() => expect(calls.find((c) => c.path.endsWith("/settings") && c.method === "PUT")?.body).toEqual({ points_watch: false }));
});

test("Overview says who is watched for points", () => {
  mockApi({});
  render(<AppProvider initialMe={ME}><PointsNote state={state({ points_watching: [{ channel: "alice", game: null, since: "2026-11-08T14:02:00Z" }] })} /></AppProvider>);
  expect(screen.getByRole("status")).toHaveTextContent("Also watching alice for channel points.");
});

test("a channel link or @name is read as the Twitch name", () => {
  expect(channelLogin("https://www.twitch.tv/Quibble_Bibble")).toBe("quibble_bibble");
  expect(channelLogin("twitch.tv/quibble_bibble/videos?filter=all")).toBe("quibble_bibble");
  expect(channelLogin("m.twitch.tv/quibble_bibble")).toBe("quibble_bibble");
  expect(channelLogin("  @Quibble_Bibble ")).toBe("quibble_bibble");
  expect(channelLogin("not a name")).toBeNull();
  expect(channelLogin("https://youtube.com/@someone")).toBeNull();
});

test("a pasted link is checked with Twitch on blur, then added without asking", async () => {
  const calls = setup();
  const u = userEvent.setup();
  const box = await screen.findByRole("combobox", { name: "Add a streamer to Channel points" });
  await u.click(box);
  await u.paste("https://www.twitch.tv/Quibble_Bibble");
  await u.tab();
  expect(await screen.findByText(/is on Twitch/)).toHaveTextContent("Quibble_Bibble is on Twitch · Offline");
  expect(box).toHaveValue("quibble_bibble");
  expect(calls.find((c) => c.path.startsWith("/api/channels/lookup"))?.path).toBe("/api/channels/lookup?login=quibble_bibble");
  await u.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ channels: ["alice", "bob", "carol", "quibble_bibble"] }));
  expect(calls.filter((c) => c.path.startsWith("/api/channels/lookup"))).toHaveLength(1);
  expect(screen.queryByText(/hasn't seen/)).toBeNull();
});

test("a name Twitch doesn't know is flagged and not added", async () => {
  const calls = setup(PAGE, undefined, true, { login: "nobody_here", found: false });
  const u = userEvent.setup();
  await u.type(await screen.findByRole("combobox", { name: "Add a streamer to Channel points" }), "nobody_here");
  await u.click(screen.getByRole("button", { name: "Add" }));
  expect(await screen.findByText(/Twitch has no channel called/)).toHaveTextContent("nobody_here");
  expect(calls.some((c) => c.method === "PUT")).toBe(false);
});

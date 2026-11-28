import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import { mockApi } from "../test/fetch";
import { campaign, state } from "../test/fixtures";
import { PrioritiesView, bestMatches, gameChoices } from "./Priorities";

const ME = { authenticated: true, setup_required: false };
function Said() {
  return <div data-testid="said">{useApp().announcement}</div>;
}
afterEach(() => vi.unstubAllGlobals());

function setup(lists: { priority: string[]; never: string[]; favourites: string[] }, put?: (b: unknown) => unknown, s = state()) {
  const calls = mockApi({
    "GET /api/state": s, "GET /api/lists": lists,
    "GET /api/suggestions": { games: ["Palia", "Phasmophobia", "007 First Light", "AION 2"], channels: [
      { login: "example_streamer", live: true, game: "Palia", last_seen: "2026-10-10T10:00:00Z" },
      { login: "dnd", live: false, game: "Dungeons & Dragons", last_seen: "2026-10-08T20:00:00Z" },
      { login: "never_seen", live: false, game: null, last_seen: null }] },
    "PUT /api/lists": put ?? ((b: unknown) => b),
  });
  render(<AppProvider initialMe={ME}><PrioritiesView /><Said /></AppProvider>);
  return calls;
}

test("moving a game keeps focus on it and announces the new position", async () => {
  const calls = setup({ priority: ["Palia", "Phasmophobia"], never: [], favourites: [] });
  const u = userEvent.setup();
  await u.click(await screen.findByRole("button", { name: "Move Phasmophobia up" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ priority: ["Phasmophobia", "Palia"] }));
  await waitFor(() => expect(screen.getByTestId("said")).toHaveTextContent("Phasmophobia moved to position 1 of 2"));
  // up is now disabled at the top, so focus lands on the next enabled control of the same row
  await waitFor(() => expect(document.activeElement?.closest(".g")?.getAttribute("data-name")).toBe("Phasmophobia"));
});

test("adding an unknown game asks first; Add anyway adds it", async () => {
  const calls = setup({ priority: [], never: [], favourites: [] });
  const u = userEvent.setup();
  await u.type(await screen.findByRole("combobox", { name: "Add a game to Priority" }), "Hollow Knight");
  await u.click(screen.getAllByRole("button", { name: "Add" })[0]!);
  expect(screen.getByText(/No game called/)).toHaveTextContent("No game called Hollow Knight has a campaign right now");
  expect(calls.some((c) => c.method === "PUT")).toBe(false);
  await u.click(screen.getByRole("button", { name: "Add anyway" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ priority: ["Hollow Knight"] }));
});

test("a known game is matched case-insensitively and added straight away", async () => {
  const calls = setup({ priority: [], never: [], favourites: [] });
  const u = userEvent.setup();
  await u.type(await screen.findByRole("combobox", { name: "Add a game to Never" }), "aion 2");
  await u.click(screen.getAllByRole("button", { name: "Add" })[2]!);
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ never: ["AION 2"] }));
});

test("a rejected save rolls back and says why", async () => {
  setup({ priority: ["Palia"], never: [], favourites: [] }, () => ({ status: 422, body: { detail: "In both Priority and Never: Palia" } }));
  const u = userEvent.setup();
  await u.click(await screen.findByRole("button", { name: "Never mine Palia" }));
  await waitFor(() => expect(screen.getByTestId("said")).toHaveTextContent("In both Priority and Never: Palia"));
  expect(document.getElementById("z-priority")).toHaveTextContent("Palia");
  expect(document.getElementById("z-never")).not.toHaveTextContent("Palia");
});

test("rows say what each game is doing", async () => {
  setup({ priority: ["Palia", "007 First Light"], never: [], favourites: ["example_streamer"] });
  expect(await screen.findByText(/Mining now · 5 h 38 min to go/)).toBeInTheDocument();
  expect(screen.getByText(/Needs account link/)).toHaveClass("g-s", "warn");
  expect(screen.getByText(/Live now · Palia/)).toBeInTheDocument();
});

test("favourites say live now, when they were last seen, or not seen yet", async () => {
  setup({ priority: [], never: [], favourites: ["example_streamer", "dnd", "never_seen"] });
  expect(await screen.findByText("Live now · Palia")).toHaveClass("on");
  expect(screen.getByText(/Offline · last seen .* on Dungeons & Dragons/)).toBeInTheDocument();
  expect(screen.getByText("Not seen live yet")).toBeInTheDocument();
});

test("the channel add box suggests offline channels too, with a note, once 3 letters are typed", async () => {
  setup({ priority: [], never: [], favourites: [] });
  const u = userEvent.setup();
  const box = await screen.findByRole("combobox", { name: "Add a favourite channel" });
  const opts = () => [...document.querySelectorAll("#opts-fav option")].map((o) => [o.getAttribute("value"), o.getAttribute("label")]);
  await u.type(box, "ex");
  expect(opts()).toEqual([]);  // nothing until 3 letters
  await u.type(box, "a");
  expect(opts()).toEqual([["example_streamer", "Live now · Palia"]]);
  await u.clear(box);
  await u.type(box, "dnd");
  expect(opts()[0]![0]).toBe("dnd");
  expect(opts()[0]![1]).toMatch(/^Offline · last seen/);
});

test("suggestions are the best few matches: whole name, then starts with, then a word in it, then anywhere", () => {
  const o = (...v: string[]) => v.map((value) => ({ value }));
  const names = o("sam_speedruns", "notspeedy", "speedrunsam", "speed", "xx", ...Array.from({ length: 20 }, (_, i) => `speedfan${i}`));
  expect(bestMatches(names, "sp")).toEqual([]);
  const got = bestMatches(names, "Speed").map((x) => x.value);
  expect(got.slice(0, 2)).toEqual(["speed", "speedfan0"]);
  expect(got).toHaveLength(8);
  expect(bestMatches(o("sam_speedruns", "notspeedy", "speedrunsam"), "speed").map((x) => x.value))
    .toEqual(["speedrunsam", "sam_speedruns", "notspeedy"]);
});

test("Never games keep their box art and say their campaign is running", async () => {
  const ow = campaign({ id: "n1", game: "Overwatch", box_art_url: "https://static-cdn.jtvnw.net/ttv-boxart/515025-{width}x{height}.jpg",
    ends_at: "2026-11-03T07:59:59Z" });
  setup({ priority: [], never: ["Overwatch", "Rise Online"], favourites: [] }, undefined, state({ never: [ow] }));
  const row = (await screen.findByText("Overwatch")).closest(".g") as HTMLElement;
  expect(row.querySelector("img.box")?.getAttribute("src")).toContain("515025-");
  expect(row.querySelector(".g-s")).toHaveTextContent(/^Campaign running · ends Tue 3 Nov$/);
  const none = (await screen.findByText("Rise Online")).closest(".g") as HTMLElement;
  expect(none.querySelector(".g-s")).toHaveTextContent("No campaign right now");
});

test("the game boxes open a list of every game with a campaign, A to Z, and a click adds it (issue #4)", async () => {
  const calls = setup({ priority: ["Palia"], never: [], favourites: [] });
  const u = userEvent.setup();
  const box = await screen.findByRole("combobox", { name: "Add a game to Priority" });
  await waitFor(() => expect(box).toHaveAttribute("aria-expanded", "false"));
  await u.click(box);
  expect(box).toHaveAttribute("aria-expanded", "true");
  const list = await screen.findByRole("listbox", { name: "Games with a campaign" });
  // Palia is already in Priority, so it isn't offered
  await waitFor(() => expect([...list.querySelectorAll("[role=option] .g-t")].map((e) => e.textContent))
    .toEqual(["007 First Light", "AION 2", "Phasmophobia"]));
  await u.click(screen.getByRole("option", { name: /AION 2/ }));
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ priority: ["Palia", "AION 2"] }));
  expect(box).toHaveAttribute("aria-expanded", "false");
});

test("typing one letter filters the game list; arrows and Enter pick, Escape closes", async () => {
  const calls = setup({ priority: [], never: [], favourites: [] });
  const u = userEvent.setup();
  const box = await screen.findByRole("combobox", { name: "Add a game to Never" });
  await u.type(box, "p");
  await waitFor(() => expect(screen.getAllByRole("option").map((o) => o.querySelector(".g-t")?.textContent))
    .toEqual(["Palia", "Phasmophobia"]));
  await u.keyboard("{Escape}");
  expect(screen.queryByRole("listbox")).toBeNull();
  await u.keyboard("{ArrowDown}{ArrowDown}");
  expect(box.getAttribute("aria-activedescendant")).toBe(screen.getByRole("option", { name: /Phasmophobia/ }).id);
  await u.keyboard("{Enter}");
  await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ never: ["Phasmophobia"] }));
});

test("a game with no campaign can still be typed and added from the picker", async () => {
  setup({ priority: [], never: [], favourites: [] });
  const u = userEvent.setup();
  await u.type(await screen.findByRole("combobox", { name: "Add a game to Priority" }), "Hollow");
  expect(screen.getByText(/No campaign matches/)).toHaveTextContent("No campaign matches Hollow. Press Add to add it anyway.");
});

test("channel boxes keep the three-letter minimum and the native list", async () => {
  setup({ priority: [], never: [], favourites: [] });
  const u = userEvent.setup();
  const box = await screen.findByRole("combobox", { name: "Add a favourite channel" });
  await u.click(box);
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(box).toHaveAttribute("list", "opts-fav");
});

test("gameChoices: everything A to Z when empty, every match best first when typed", () => {
  const o = (...v: string[]) => v.map((value) => ({ value }));
  expect(gameChoices(o("b", "C", "a"), " ").map((x) => x.value)).toEqual(["a", "b", "C"]);
  const many = o(...Array.from({ length: 30 }, (_, i) => `game ${i}`));
  expect(gameChoices(many, "g")).toHaveLength(30);
  expect(gameChoices(o("sam_speedruns", "speed"), "spe").map((x) => x.value)).toEqual(["speed", "sam_speedruns"]);
});

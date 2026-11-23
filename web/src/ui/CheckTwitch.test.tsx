import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider } from "../store";
import { mockApi } from "../test/fetch";
import { state } from "../test/fixtures";
import { CheckTwitch } from "./CheckTwitch";

const ME = { authenticated: true, setup_required: false };
afterEach(() => vi.unstubAllGlobals());

function setup(refresh: unknown = undefined) {
  const calls = mockApi({ "GET /api/state": state(), "POST /api/refresh": refresh });
  render(<AppProvider initialMe={ME}><CheckTwitch /></AppProvider>);
  return calls;
}

test("Check Twitch re-reads campaigns now, says so, and refreshes the page's state", async () => {
  const calls = setup();
  const btn = await screen.findByRole("button", { name: "Check Twitch" });
  await act(async () => { await userEvent.click(btn); });
  expect(calls.filter((c) => c.method === "POST" && c.path === "/api/refresh")).toHaveLength(1);
  expect(await screen.findByText("Checked")).toBeInTheDocument();
  await waitFor(() => expect(calls.filter((c) => c.path === "/api/state").length).toBeGreaterThan(1));
});

test("a second click while it's still checking sends nothing", async () => {
  let release: () => void = () => undefined;
  const slow = new Promise<void>((r) => { release = r; });
  const calls = mockApi({ "GET /api/state": state() });
  const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const real = fetchMock.getMockImplementation() as (url: string, init?: RequestInit) => Promise<Response>;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (String(url) === "api/refresh") { calls.push({ method: "POST", path: "/api/refresh", body: undefined }); await slow; return new Response(null, { status: 204 }); }
    return real(url, init);
  });
  render(<AppProvider initialMe={ME}><CheckTwitch /></AppProvider>);
  const btn = await screen.findByRole("button", { name: "Check Twitch" });
  await userEvent.click(btn);
  expect(await screen.findByText("Checking…")).toBeInTheDocument();
  expect(btn).toHaveAttribute("aria-disabled", "true");
  await userEvent.click(btn);
  expect(calls.filter((c) => c.path === "/api/refresh")).toHaveLength(1);
  await act(async () => { release(); });
  expect(await screen.findByText("Checked")).toBeInTheDocument();
});

test("a failed check says why", async () => {
  setup({ status: 409, body: { detail: "Not signed in to Twitch." } });
  await act(async () => { await userEvent.click(await screen.findByRole("button", { name: "Check Twitch" })); });
  expect(await screen.findByText("Couldn't check")).toBeInTheDocument();
});

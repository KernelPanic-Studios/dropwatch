import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, Toasts } from "../store";
import { mockApi } from "../test/fetch";
import { state } from "../test/fixtures";
import { pageFolder, proxySnippet } from "./Proxy";
import { SettingsView } from "./Settings";

afterEach(() => vi.unstubAllGlobals());

const DIRECT = { hosts: [], trusted: [], host: "192.168.1.10:5800", host_is_local: true, scheme: "http",
  client: "192.168.1.20", forwarded_for: null, proxy_trusted: null, prefix: null };

function setup(proxy: Record<string, unknown>) {
  location.hash = "#settings/proxy";
  mockApi({ "GET /api/state": state(), "GET /api/settings": {}, "GET /api/proxy": { ...DIRECT, ...proxy } });
  render(<AppProvider initialMe={{ authenticated: true, setup_required: false }}><SettingsView /><Toasts /></AppProvider>);
}

test("opened by address: no proxy, nothing listed, and the example points at this server", async () => {
  setup({});
  expect(await screen.findByText("Opened directly, without a proxy")).toBeInTheDocument();
  expect(screen.getByText(/None listed\./)).toBeInTheDocument();
  const ex = screen.getByLabelText("nginx / SWAG example");
  expect(ex).toHaveTextContent("proxy_pass http://192.168.1.10:5800;");
  expect(ex).toHaveTextContent("server_name dropwatch.example.com;");
  expect(screen.getByText(/Replace dropwatch\.example\.com with your own\./)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Caddy" }));
  expect(screen.getByLabelText("Caddy example")).toHaveTextContent("reverse_proxy 192.168.1.10:5800");
});

test("an untrusted proxy is called out with the line to add", async () => {
  setup({ host: "dropwatch.example.com", host_is_local: false, hosts: ["dropwatch.example.com"], client: "172.18.0.5",
    forwarded_for: "203.0.113.7", proxy_trusted: false });
  expect(await screen.findByText("Opened through a reverse proxy")).toBeInTheDocument();
  expect(screen.getByText(/isn't trusted/)).toHaveTextContent("The proxy at 172.18.0.5 isn't trusted.");
  expect(screen.getByText("FORWARDED_ALLOW_IPS=172.18.0.5")).toBeInTheDocument();
  const ex = screen.getByLabelText("nginx / SWAG example");
  expect(ex).toHaveTextContent("server_name dropwatch.example.com;");
  expect(ex).toHaveTextContent("proxy_pass http://SERVER_IP:5800;");
});

test("a trusted proxy shows the visitor's own address", async () => {
  setup({ host: "dropwatch.example.com", host_is_local: false, client: "203.0.113.7", forwarded_for: "203.0.113.7",
    proxy_trusted: true, trusted: ["172.18.0.5"], scheme: "https" });
  const ok = await screen.findByText(/The proxy is trusted/);
  expect(within(ok).getByText("203.0.113.7")).toBeInTheDocument();
  expect(screen.getByText("172.18.0.5")).toBeInTheDocument();
});

test("pageFolder: empty at the root, the folder with its slash otherwise", () => {
  expect(pageFolder("/")).toBe("");
  expect(pageFolder("/index.html")).toBe("");
  expect(pageFolder("/dropwatch/")).toBe("/dropwatch/");
  expect(pageFolder("/apps/dropwatch/")).toBe("/apps/dropwatch/");
});

test("subfolder snippets strip the folder and send the bare folder to the slash", () => {
  const t = { name: "home.example.org", folder: "/dropwatch/", upstream: "SERVER_IP:5800" };
  const nginx = proxySnippet("nginx", t);
  expect(nginx).toContain("server_name home.example.org;");
  expect(nginx).toContain("location = /dropwatch { return 301 /dropwatch/; }");
  expect(nginx).toContain("proxy_pass http://SERVER_IP:5800/;");
  expect(proxySnippet("caddy", t)).toContain("handle_path /dropwatch/* {");
  expect(proxySnippet("traefik", t)).toContain("stripprefix.prefixes=/dropwatch");
  expect(proxySnippet("traefik", t)).toContain("Host(`home.example.org`) && PathPrefix(`/dropwatch`)");
  expect(proxySnippet("npm", t)).toContain("location /dropwatch/ {");
  // the placeholder name becomes a bare site in a folder
  expect(proxySnippet("nginx", { ...t, name: "dropwatch.example.com" })).toContain("server_name example.com;");
});

test("the page asks for the API relative to itself, so a subfolder works (issue #5)", async () => {
  const seen: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => { seen.push(String(url)); return new Response("{}", { status: 200 }); }));
  const { api } = await import("../api/client");
  await api.get("/state");
  expect(seen).toEqual(["api/state"]);
});

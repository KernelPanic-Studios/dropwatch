/** Route-table fetch stub for component tests: "GET /api/state" -> body (or a function of the body sent). */
type Handler = unknown | ((body: unknown) => unknown);
export function mockApi(routes: Record<string, Handler | { status: number; body?: unknown }>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = String(url).replace(/^api\//, "/api/");  // the page asks relative to itself
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    const key = `${method} ${path.split("?")[0]}`;
    if (!(key in routes)) return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    let r = routes[key];
    if (typeof r === "function") r = (r as (b: unknown) => unknown)(body);
    if (r && typeof r === "object" && "status" in (r as object) && typeof (r as { status: unknown }).status === "number") {
      const { status, body: b } = r as { status: number; body?: unknown };
      return new Response(b === undefined ? null : JSON.stringify(b), { status });
    }
    return r === undefined ? new Response(null, { status: 204 }) : new Response(JSON.stringify(r), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

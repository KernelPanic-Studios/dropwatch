import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { Mark } from "./Icons";

const repo = resolve(__dirname, "../../..");
const read = (p: string) => readFileSync(resolve(repo, p));

test("the top-bar mark draws exactly the logo's paths (brand/mark/dropwatch-mark.svg)", () => {
  const svg = read("brand/mark/dropwatch-mark.svg").toString();
  const want = [...svg.matchAll(/<path d="([^"]+)"/g)].map((m) => m[1]);
  const { container } = render(<Mark />);
  const got = [...container.querySelectorAll("path")].map((p) => p.getAttribute("d"));
  expect(want.length).toBe(9);
  expect(got).toEqual(want);
  expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
});

test("the files the browser loads are the logo set's own, byte for byte", () => {
  for (const [served, source] of [
    ["favicon.ico", "icon/favicon.ico"], ["apple-touch-icon.png", "icon/apple-touch-icon.png"],
    ["dropwatch-mark.svg", "mark/dropwatch-mark.svg"], ["icon-192.png", "png/icon-192.png"],
    ["icon-512.png", "png/icon-512.png"], ["icon-maskable-192.png", "png/icon-maskable-192.png"],
    ["icon-maskable-512.png", "png/icon-maskable-512.png"],
  ]) {
    expect(read(`web/public/${served}`).equals(read(`brand/${source}`)), served).toBe(true);
  }
});

test("index.html links the icons and the manifest lists real files", () => {
  const html = read("web/index.html").toString();
  for (const href of ["/favicon.ico", "/dropwatch-mark.svg", "/apple-touch-icon.png", "/manifest.webmanifest"]) {
    expect(html).toContain(`href="${href}"`);
  }
  const manifest = JSON.parse(read("web/public/manifest.webmanifest").toString());
  // relative to the manifest, so they also resolve in a subfolder (issue #5)
  for (const icon of manifest.icons) expect(() => read(`web/public/${icon.src}`)).not.toThrow();
  expect(manifest.icons.every((i: { src: string }) => !i.src.startsWith("/"))).toBe(true);
  expect(manifest.start_url).toBe("./");
  expect(manifest.icons.filter((i: { purpose: string }) => i.purpose === "maskable")).toHaveLength(2);
});

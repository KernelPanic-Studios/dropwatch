import { NB, boxArt, dur, mark, span } from "./format";

test("durations use non-breaking spaces", () => {
  expect(dur(45)).toBe(`45${NB}min`);
  expect(dur(111)).toBe(`1${NB}h 51${NB}min`);
  expect(dur(120)).toBe(`2${NB}h`);
  expect(dur(-3)).toBe(`0${NB}min`);
});

test("track marks", () => {
  expect(mark(30)).toBe(`30${NB}min`);
  expect(mark(60)).toBe(`1${NB}h`);
  expect(mark(90)).toBe(`1.5${NB}h`);
});

test("long spans switch to days", () => {
  expect(span(3 * 24 * 60 + 4 * 60)).toBe(`3${NB}d 4${NB}h`);
  expect(span(90)).toBe(`1${NB}h 30${NB}min`);
});

test("box art gets a size", () => {
  expect(boxArt("https://static-cdn.jtvnw.net/ttv-boxart/460630.jpg")).toBe(
    "https://static-cdn.jtvnw.net/ttv-boxart/460630-144x192.jpg",
  );
  expect(boxArt("https://x/ttv-boxart/1-{width}x{height}.jpg")).toBe("https://x/ttv-boxart/1-144x192.jpg");
  expect(boxArt("https://x/ttv-boxart/1-120x160.jpg")).toBe("https://x/ttv-boxart/1-144x192.jpg");
  expect(boxArt("")).toBe("");
  // History's kept copies are already the right size: left alone
  expect(boxArt("api/img/0123456789abcdef01234567.jpg")).toBe("api/img/0123456789abcdef01234567.jpg");
});

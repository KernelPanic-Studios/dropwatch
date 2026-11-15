"""Generate the docs' reference tables from the code (docs/adr/0014-generate-reference-tables-in-the-docs.md).

Hand-written pages carry marker pairs:

    <!-- generated:<kind> [id] -->
    ...rewritten by this script...
    <!-- /generated:<kind> -->

and docs/third-party-packages.md is written whole. Run from the repository root:

    uv run python scripts/gen_docs.py            # rewrite
    uv run python scripts/gen_docs.py --check    # exit 1 when anything is stale

tests/test_docs_generated.py runs the check in the normal test run.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
import typing
from collections import Counter
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dropwatch.api.models import SettingsIn  # noqa: E402
from dropwatch.notify import CHANNELS  # noqa: E402
from dropwatch.store import SETTING_DEFAULTS, SETTINGS  # noqa: E402

PAGES = (ROOT / "docs" / "guides" / "configuration.md", ROOT / "docs" / "guides" / "notifications.md")
PACKAGES_PAGE = ROOT / "docs" / "third-party-packages.md"
BLOCK = re.compile(r"(<!-- generated:([a-z-]+)(?: ([A-Za-z0-9_-]+))? -->\n)(.*?)(<!-- /generated:\2 -->)",
                   re.S)

# licences a runtime dependency may carry; a new one fails the test until it is added here, in review
ALLOWED_LICENCES = {"MIT", "MIT-0", "0BSD", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0",
                    "Apache-2.0 AND MIT", "PSF-2.0"}
_LICENCE_NAMES = {"MIT License": "MIT", "Apache Software License": "Apache-2.0", "Apache 2.0": "Apache-2.0",
                  "Apache License 2.0": "Apache-2.0", "Python Software Foundation License": "PSF-2.0",
                  "ISC License (ISCL)": "ISC"}


class UnknownId(ValueError):
    pass


# --- block generators: kind -> (id or None) -> markdown


def _allowed(key: str) -> str:
    field = SettingsIn.model_fields.get(key)
    if field is None:
        return "(not settable from the page)"
    lo = next((m.ge for m in field.metadata if hasattr(m, "ge") and m.ge is not None), None)
    hi = next((m.le for m in field.metadata if hasattr(m, "le") and m.le is not None), None)
    if lo is not None and hi is not None:
        return f"{lo} to {hi}"
    for arg in typing.get_args(field.annotation):
        if typing.get_origin(arg) is typing.Literal:
            return ", ".join(str(v) for v in typing.get_args(arg))
    if key.endswith("_tz"):
        return 'an IANA zone name, or "" for the server\'s zone'
    return "true, false" if SETTINGS[key] is bool else "any"


def settings_table(ident: str | None) -> str:
    if ident is not None:
        raise UnknownId(f"settings takes no id, got {ident!r}")
    rows = ["| Key | Type | Default | Allowed |", "|---|---|---|---|"]
    for key, kind in SETTINGS.items():
        default = SETTING_DEFAULTS[key]
        shown = json.dumps(default) if isinstance(default, (bool, str)) else str(default)
        rows.append(f"| `{key}` | {kind.__name__} | `{shown}` | {_allowed(key)} |")
    return "\n".join(rows) + "\n"


def notify_catalogue(ident: str | None) -> str:
    if ident is not None:
        raise UnknownId(f"notify-catalogue takes no id, got {ident!r}")
    rows = ["| Service | Type key | Fields | Page |", "|---|---|---|---|"]
    for kind, spec in CHANNELS.items():
        fields = ", ".join(f"`{f.key}`" + (" (secret)" if f.secret else "") for f in spec.fields)
        rows.append(f"| {spec.name} | `{kind}` | {fields} | [{spec.name}](#{kind}) |")
    return "\n".join(rows) + "\n"


def notify_fields(ident: str | None) -> str:
    spec = CHANNELS.get(ident or "")
    if spec is None:
        raise UnknownId(f"no notification channel called {ident!r}")
    rows = ["| Field | Label on the page | Secret |", "|---|---|---|"]
    rows += [f"| `{f.key}` | {f.label} | {'yes' if f.secret else 'no'} |" for f in spec.fields]
    return "\n".join(rows) + f"\n\n{spec.hint}\n"


GENERATORS: dict[str, Callable[[str | None], str]] = {
    "settings": settings_table, "notify-catalogue": notify_catalogue, "notify-fields": notify_fields}


def render(text: str) -> str:
    """The page with every marked block regenerated. Raises UnknownId for a marker the code can't fill."""
    def fill(m: re.Match) -> str:
        kind, ident = m.group(2), m.group(3)
        gen = GENERATORS.get(kind)
        if gen is None:
            raise UnknownId(f"no generator for {kind!r}")
        return m.group(1) + gen(ident) + m.group(5)
    return BLOCK.sub(fill, text)


def blocks(text: str) -> list[tuple[str, str | None]]:
    return [(m.group(2), m.group(3)) for m in BLOCK.finditer(text)]


# --- third-party packages


def _licence(name: str) -> str:
    try:
        m = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "unknown (not installed)"
    if expr := (m.get("License-Expression") or "").strip():
        return expr
    raw = (m.get("License") or "").strip()
    if raw and "\n" not in raw and len(raw) < 40:
        return _LICENCE_NAMES.get(raw, raw)
    for c in m.get_all("Classifier") or []:
        if c.startswith("License ::"):
            return _LICENCE_NAMES.get(c.split(" :: ")[-1], c.split(" :: ")[-1])
    return "unknown"


def python_runtime() -> list[tuple[str, str, str]]:
    """(name, version, licence) for dropwatch's runtime closure in uv.lock: no extras, no dev group."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    pk = {p["name"]: p for p in lock["package"]}
    seen: dict[str, dict] = {}

    def walk(name: str) -> None:
        if name in seen:
            return
        seen[name] = pk[name]
        for d in pk[name].get("dependencies", []):
            walk(d["name"])
    for d in pk["dropwatch"].get("dependencies", []):
        walk(d["name"])
    return [(n, p["version"], _licence(n)) for n, p in sorted(seen.items())]


def npm_runtime() -> list[tuple[str, str, str]]:
    """(name, version, licence) for the page's runtime closure in package-lock.json (no devDependencies)."""
    lock = json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
    pk = lock["packages"]
    seen: dict[str, dict] = {}

    def walk(name: str, parent: str) -> None:
        nested = f"{parent}/node_modules/{name}"
        path = nested if parent and nested in pk else f"node_modules/{name}"
        if path in seen or path not in pk:
            return
        e = seen[path] = pk[path]
        optional = {k for k, v in (e.get("peerDependenciesMeta") or {}).items() if v.get("optional")}
        for d in [*(e.get("dependencies") or {}), *(e.get("peerDependencies") or {})]:
            if d not in optional:
                walk(d, path)
    for d in pk[""].get("dependencies") or {}:
        walk(d, "")
    return sorted((p.split("node_modules/")[-1], e.get("version", ""), e.get("license") or "unknown")
                  for p, e in seen.items())


def packages_page() -> str:
    py, js = python_runtime(), npm_runtime()
    out = ["<!-- Generated by `uv run python scripts/gen_docs.py` from `uv.lock`, the installed packages' "
           "metadata and `web/package-lock.json`. Do not edit by hand: `tests/test_docs_generated.py` "
           "fails until this file matches a fresh run. -->", "",
           "# Third-party packages", "",
           "The runtime dependencies only: what the Docker image installs (`uv sync --frozen --no-dev`) and "
           "what the page depends on (`dependencies` in `web/package.json`), with everything they pull in. "
           "Development tools, the optional `browser` extra and the test suites are left out. The page's "
           "list is the lockfile's closure; the built bundle includes less, because Vite drops what the "
           "page never imports.", "",
           "Licences come from each Python package's installed metadata and from `package-lock.json`. "
           "Every licence must be one of `ALLOWED_LICENCES` in `scripts/gen_docs.py`; the test fails on "
           "any other.", ""]
    for title, rows in (("Python (the miner)", py), ("JavaScript (the page)", js)):
        counts = Counter(lic for _, _, lic in rows)
        by_count = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        summary = ", ".join(f"{lic} {n}" for lic, n in by_count)
        out += [f"## {title}", "", f"{len(rows)} packages: {summary}.", "",
                "| Package | Version | Licence |", "|---|---|---|"]
        out += [f"| `{n}` | {v} | {lic} |" for n, v, lic in rows]
        out.append("")
    return "\n".join(out)


def bad_licences() -> list[str]:
    rows = (*python_runtime(), *npm_runtime())
    return [f"{n} {v}: {lic}" for n, v, lic in rows if lic not in ALLOWED_LICENCES]


# --- entry point


def stale() -> list[Path]:
    out = [p for p in PAGES if render(p.read_text(encoding="utf-8")) != p.read_text(encoding="utf-8")]
    if not PACKAGES_PAGE.exists() or PACKAGES_PAGE.read_text(encoding="utf-8") != packages_page():
        out.append(PACKAGES_PAGE)
    return out


def main(argv: list[str]) -> int:
    if "--check" in argv:
        old = stale()
        for p in old:
            print(f"stale: {p.relative_to(ROOT)} (run: uv run python scripts/gen_docs.py)")
        for b in bad_licences():
            print(f"licence not allowed: {b}")
        return 1 if old or bad_licences() else 0
    for p in PAGES:
        p.write_text(render(p.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    PACKAGES_PAGE.write_text(packages_page(), encoding="utf-8", newline="\n")
    print("wrote " + ", ".join(str(p.relative_to(ROOT)) for p in (*PAGES, PACKAGES_PAGE)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

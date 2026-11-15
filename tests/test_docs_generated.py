"""The docs' generated tables match the code (docs/adr/0014-generate-reference-tables-in-the-docs.md).

Fix a failure with: uv run python scripts/gen_docs.py, then commit the result.
"""
import importlib.util
from pathlib import Path

import pytest

from dropwatch.notify import CHANNELS

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("gen_docs", ROOT / "scripts" / "gen_docs.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _pages() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in gen.PAGES}


def test_the_check_can_read_the_pages():
    # a clean result only means something if the markers were found
    found = [b for text in _pages().values() for b in gen.blocks(text)]
    assert len(found) >= 2 + len(CHANNELS), found
    assert ("settings", None) in found


def test_the_check_catches_a_stale_block_and_an_unknown_id():
    text = next(iter(_pages().values()))
    stale = text.replace("<!-- /generated:", "a stale line\n<!-- /generated:", 1)
    assert gen.render(stale) != stale
    with pytest.raises(gen.UnknownId):
        gen.render("<!-- generated:notify-fields no-such-service -->\n<!-- /generated:notify-fields -->")
    with pytest.raises(gen.UnknownId):
        gen.render("<!-- generated:no-such-kind -->\n<!-- /generated:no-such-kind -->")


def test_generated_blocks_are_fresh():
    for path, text in _pages().items():
        assert gen.render(text) == text, f"{path.name} is stale: run uv run python scripts/gen_docs.py"


def test_every_notification_service_has_a_page_section():
    text = (ROOT / "docs" / "guides" / "notifications.md").read_text(encoding="utf-8")
    documented = {ident for kind, ident in gen.blocks(text) if kind == "notify-fields"}
    assert documented == set(CHANNELS)


def test_third_party_packages_page_is_fresh():
    assert gen.PACKAGES_PAGE.read_text(encoding="utf-8") == gen.packages_page(), \
        "run: uv run python scripts/gen_docs.py"


def test_every_runtime_licence_is_allowed():
    assert gen.bad_licences() == []

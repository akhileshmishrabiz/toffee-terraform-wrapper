"""Documentation structure, CLI drift, and local asset safety checks."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
MKDOCS = ROOT / "mkdocs.yml"


def _docs_text():
    return "\n".join(path.read_text() for path in sorted(DOCS.glob("*.md")))


def test_mkdocs_nav_and_all_local_references_exist():
    config = MKDOCS.read_text()
    nav_pages = set(re.findall(r": ([a-z0-9-]+\.md)$", config, re.MULTILINE))
    pages = {path.name for path in DOCS.glob("*.md")}

    assert nav_pages == pages
    assert "site_url: https://akhileshmishrabiz.github.io/" in config

    references = []
    for page in DOCS.glob("*.md"):
        text = page.read_text()
        references.extend(
            (page, target)
            for target in re.findall(
                r"(?:\[[^\]]*\]\(|(?:href|src)=[\"'])([^\"') >]+)", text
            )
            if not target.startswith(("https://", "http://", "mailto:", "#"))
        )

    for page, target in references:
        path = target.split("#", 1)[0]
        if not path:
            continue
        if path.endswith("/"):
            path = path.rstrip("/") + ".md"
        assert (page.parent / path).exists(), f"{page.name}: missing {target}"

    for path in re.findall(
        r"(?:logo|favicon|extra_css):? ?(?:\n +-)?? ?([^\s]+)", config
    ):
        if path.startswith(("http:", "https:")):
            continue
        assert (DOCS / path).exists(), f"mkdocs.yml: missing {path}"


def test_documented_commands_and_new_help_match_cli(invoke):
    docs = _docs_text()
    for command in (
        "toffee new service",
        "toffee dev init",
        "toffee dev plan",
        "toffee prod apply -auto-approve",
        "toffee diff dev prod --exit-code",
        "toffee env copy dev staging",
    ):
        assert command in docs

    help_result = invoke("new", "--help")
    assert help_result.exit_code == 0
    assert "Usage: app new [OPTIONS] [DIRECTORY]" in help_result.stdout
    assert help_result.stdout.count("--help") == 1

    for removed in (
        "--name",
        "--envs",
        "--provider",
        "--backend",
        "--region",
        "--dry-run",
        "--agents",
        "--template",
    ):
        assert removed not in docs


def test_required_safety_guidance_is_present():
    docs = _docs_text().lower()
    for statement in (
        "do **not**\nbypass this confirmation",
        "shared-state refusal",
        "another machine",
        "change-me",
        "status 1 means differences and status 2 means an error",
        "sensitive-looking values are redacted",
    ):
        assert statement in docs


def test_svg_assets_are_safe_and_self_contained():
    assets = list((DOCS / "assets").glob("*.svg"))
    assert len(assets) >= 4

    for asset in assets:
        text = asset.read_text()
        ET.fromstring(text)
        lowered = text.lower()
        assert "<script" not in lowered
        assert "file://" not in lowered
        assert "/users/" not in lowered
        assert "/home/" not in lowered
        assert "-----begin " not in lowered
        assert not re.search(r"(?:href|src)=[\"']https?://", text)
        assert not re.search(
            r"\b(?:aws_access_key_id|secret_access_key|github_pat)\b", lowered
        )


def test_docs_css_has_responsive_mobile_layout():
    css = (DOCS / "stylesheets/extra.css").read_text()
    assert "@media (max-width:" in css
    assert "grid-template-columns: 1fr" in css
    assert "width: 1200px" not in css

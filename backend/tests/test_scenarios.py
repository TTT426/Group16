"""Sanity checks for the simulated-workspace scenarios used in the evaluation."""

import re
from pathlib import Path

import pytest
import yaml

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_workspace"
SCENARIOS = sorted(SCENARIO_DIR.glob("scenario_*.yaml"))
PLACEHOLDER = re.compile(r"\{\{\s*([a-z]+\.[a-z]+\.[\w-]+)\s*\}\}")


def _defined_refs(s: dict) -> set[str]:
    refs = set()
    refs |= {f"github.issue.{i['key']}" for i in s["github"].get("issues", [])}
    refs |= {f"github.pull.{p['key']}" for p in s["github"].get("pulls", [])}
    refs |= {f"notion.page.{p['key']}" for p in s["notion"]["pages"]}
    for ch in s["discord"]["channels"]:
        refs |= {f"discord.thread.{t['key']}" for t in ch["threads"]}
    return refs


def test_two_scenarios_exist():
    assert len(SCENARIOS) >= 2


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_references_resolve(path):
    text = path.read_text(encoding="utf-8")
    scenario = yaml.safe_load(text)
    defined = _defined_refs(scenario)

    used = set(PLACEHOLDER.findall(text))
    assert used, "scenario should cross-link tools"
    assert used <= defined, f"undefined references: {used - defined}"

    sources = set(scenario["answer_key"]["sources"])
    assert sources <= defined
    # The answer must require all three tools, otherwise integration is not being tested.
    assert {s.split(".")[0] for s in sources} == {"github", "notion", "discord"}
    for part in ("cause", "current_approach", "why"):
        assert scenario["answer_key"][part]

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import dimwit.director as director_module
from dimwit.director import Director


class _State:
    def __str__(self):
        return "PROMOTED_TO_REVIEW"


class _Result:
    state = _State()
    score = 1.0


class _Pipeline:
    def __init__(self, fail=False):
        self.fail = fail

    def run(self, task):
        if self.fail:
            raise RuntimeError("synthetic pipeline crash")
        return _Result()


def test_sweep_isolates_pipeline_exception_and_continues(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="dimwit_director_resilience_"))
    monkeypatch.setattr(director_module, "list_pipelines", lambda: ["bad", "good"])
    monkeypatch.setattr(director_module, "get_pipeline", lambda name: _Pipeline(fail=name == "bad"))
    director = Director(ledger_path=tmp / "director.jsonl", breaker_path=tmp / "breaker.json")
    monkeypatch.setattr(director, "validate_everything",
                        lambda domains=None: {"suite_verdict": "PASS", "counts": {"PASS": 1}})
    result = director.run_sweep([
        {"pipeline": "bad", "asset_id": "one", "priority": 2},
        {"pipeline": "good", "asset_id": "two", "priority": 1},
    ])
    assert any(row["pipeline"] == "bad" and "execution error" in row["why"] for row in result["blocked"])
    assert any(row["pipeline"] == "good" and row["state"] == "PROMOTED_TO_REVIEW" for row in result["ran"])


def test_breaker_is_per_asset_not_per_pipeline(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="dimwit_director_breaker_"))
    breaker_path = tmp / "breaker.json"
    breaker_path.write_text(json.dumps({"same:bad_asset": 3}), encoding="utf-8")
    monkeypatch.setattr(director_module, "list_pipelines", lambda: ["same"])
    monkeypatch.setattr(director_module, "get_pipeline", lambda name: _Pipeline())
    director = Director(breaker_threshold=3, ledger_path=tmp / "director.jsonl", breaker_path=breaker_path)
    monkeypatch.setattr(director, "validate_everything",
                        lambda domains=None: {"suite_verdict": "PASS", "counts": {"PASS": 1}})
    result = director.run_sweep([
        {"pipeline": "same", "asset_id": "bad_asset", "priority": 2},
        {"pipeline": "same", "asset_id": "good_asset", "priority": 1},
    ])
    assert [row["asset"] for row in result["ran"]] == ["good_asset"]

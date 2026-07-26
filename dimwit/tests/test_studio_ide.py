from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import pytest

from dimwit.studio_ide.server import (
    ACTION_COMMANDS,
    STATIC,
    build_workspace_state,
    create_server,
    read_source,
    redact_output,
    search_source,
)


def test_workspace_state_exposes_game_production_truth_without_new_authority():
    state = build_workspace_state()
    assert state["local_only"] is True
    assert state["review_ceiling"] == "PROMOTED_TO_REVIEW"
    assert state["studio"]["total"] == 22
    assert state["capabilities"]["count"] >= 20
    assert state["validation"]["verdict"] in {"PASS", "FAIL", "BLOCKED", "REJECTED", "NOT_RUN"}
    assert state["evolution"]["authority"] == "ADVISORY_ONLY"
    assert state["ecosystem"]["state"] == "PASS"
    assert state["engines"]["adapter_count"] == 8
    assert state["engines"]["conformance"]["state"] == "CI_CONTRACTED"
    assert state["improvement_outcomes"]["authority"] == "HUMAN_REVIEWER_ONLY"
    assert state["cross_engine"]["state"] in {"PASS", "BLOCKED", "NOT_RUN"}
    assert state["mobile"]["quality"]["check_count"] >= 60


def test_action_surface_is_fixed_and_contains_no_execution_or_provider_lane():
    assert set(ACTION_COMMANDS) == {
        "studio_plan", "improvement_plan", "ecosystem_audit", "slice_tests", "validate_full",
        "engine_audit", "mobile_audit",
    }
    flattened = json.dumps(ACTION_COMMANDS).lower()
    assert "--execute" not in flattened
    assert "provider" not in flattened
    assert "shell=true" not in flattened


def test_source_reader_is_confined_to_first_party_roots():
    matches = search_source("studio_ide")
    assert matches
    assert all(row["path"].startswith(("dimwit/", "config/", "docs/")) for row in matches)
    source = read_source("dimwit/studio_ide/server.py")
    assert source["bytes"] > 0
    with pytest.raises(ValueError):
        read_source("../Blunder/README.md")
    with pytest.raises(ValueError):
        read_source(".git/config")


def test_redaction_masks_secret_like_output():
    result = redact_output("api_key=super-secret-value\nstatus=ok")
    assert "super-secret-value" not in result
    assert "[REDACTED]" in result


def test_static_workspace_has_all_four_ide_views_and_no_external_assets():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert all(f'data-view="{name}"' in html for name in ("forge", "studio", "engines", "mobile", "evolve", "source"))
    assert "https://" not in html
    assert '<script src="/app.js" defer></script>' in html


def test_http_api_requires_token_and_health_is_minimal():
    server = create_server(0, token="test-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as response:
            assert json.loads(response.read())["local_only"] is True
        with urllib.request.urlopen(base + "/favicon.ico", timeout=5) as response:
            assert response.status == 204
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base + "/api/state", timeout=5)
        assert exc.value.code == 401
        request = urllib.request.Request(base + "/api/state", headers={"X-Dimwit-Token": "test-token"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
            assert payload["product"] == "DIMWIT STUDIO"
            assert response.headers["X-Frame-Options"] == "DENY"
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_binds_loopback_only():
    server = create_server(0, token="test")
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()

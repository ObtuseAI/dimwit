"""SELF_METRICS_AND_QUEUE_DIRECTOR_V1 (masterplan bundle 9) — RED-first contract tests.

Pure functions over a synthetic validation report: self-metrics derivation, the evidence-freshness
radar classification, and the deterministic evidence-ranked operational queue. Fixtures are
synthetic dicts (snapshot law — no live report is read or mutated).
"""
from __future__ import annotations

from dimwit.pipelines.self_metrics import (
    DEFAULT_MAX_AGE_SECONDS,
    WARN_HEADROOM_SECONDS,
    build_artifact,
    compute_freshness_radar,
    compute_self_metrics,
    rank_operational_queue,
    recompute_and_compare,
)


def _res(vid, domain, state, probe="static_python", age=None, max_age=None):
    detail = {}
    if age is not None:
        detail["age_seconds"] = age
    if max_age is not None:
        detail["max_age_seconds"] = max_age
    return {"validator_id": vid, "domain": domain, "state": state, "probe_type": probe,
            "severity": "blocker", "detail": detail}


def _report(results, verdict="PASS", run_ts=1783000000):
    return {"suite_verdict": verdict, "run_ts": run_ts, "results": results}


HOUR = 3600


def _mixed_report():
    return _report([
        _res("a_ok", "alpha", "PASS"),
        _res("b_ok", "alpha", "PASS", probe="filesystem"),
        _res("c_bad", "beta", "BLOCKED", probe="ue_python"),
        # a fresh aged lane (lots of headroom), a warn lane (near ceiling), a stale lane (over)
        _res("perf_baseline_result_fresh", "performance_baseline", "PASS", probe="filesystem",
             age=1 * HOUR),                        # 6h ceiling -> 5h headroom -> fresh
        _res("bot_balance_result_fresh", "bot_balance", "PASS", probe="filesystem",
             age=5 * HOUR),                        # 6h ceiling -> 1h headroom -> warn
        _res("anim_video_motion_live", "anim_live", "PASS", probe="perception",
             age=13 * HOUR),                       # 12h ceiling -> -1h -> stale
    ], verdict="BLOCKED")


# ------------------------------------------------------------------ self metrics

def test_domains_and_counts():
    m = compute_self_metrics(_mixed_report())
    assert m["suite"]["total"] == 6
    assert m["domains"]["alpha"]["healthy"] is True
    assert m["domains"]["beta"]["healthy"] is False
    assert m["suite"]["counts"]["BLOCKED"] == 1


def test_probe_mix_counts_runtime_vs_static():
    m = compute_self_metrics(_mixed_report())
    assert m["probe_mix"]["ue_python"] == 1
    assert m["probe_mix"]["perception"] == 1
    assert m["probe_mix"]["filesystem"] == 3


# ------------------------------------------------------------------ freshness radar

def test_radar_classifies_fresh_warn_stale():
    radar = {e["validator_id"]: e for e in compute_freshness_radar(_mixed_report())}
    assert radar["perf_baseline_result_fresh"]["status"] == "fresh"
    assert radar["bot_balance_result_fresh"]["status"] == "warn"
    assert radar["anim_video_motion_live"]["status"] == "stale"


def test_radar_uses_embedded_max_age_when_present():
    rep = _report([_res("x", "d", "PASS", probe="filesystem", age=2 * HOUR, max_age=2.5 * HOUR)])
    e = compute_freshness_radar(rep)[0]
    assert e["max_age_seconds"] == 2.5 * HOUR
    assert e["status"] == "warn"          # 0.5h headroom < 2h WARN


def test_radar_skips_ageless_validators():
    rep = _report([_res("static_one", "d", "PASS")])
    assert compute_freshness_radar(rep) == []


def test_radar_default_ceiling_for_unknown_aged_lane():
    rep = _report([_res("unknown_fresh", "d", "PASS", probe="filesystem", age=1 * HOUR)])
    e = compute_freshness_radar(rep)[0]
    assert e["max_age_seconds"] == DEFAULT_MAX_AGE_SECONDS


# ------------------------------------------------------------------ operational queue

def test_queue_orders_broken_then_stale_then_warn():
    q = rank_operational_queue(build_artifact(_mixed_report(), {}))
    buckets = [it["bucket"] for it in q]
    assert buckets[0] == "broken"
    # broken (beta) must precede any stale/warn re-run
    assert buckets.index("broken") < buckets.index("stale") < buckets.index("warn")


def test_queue_items_cite_evidence_and_command():
    q = rank_operational_queue(build_artifact(_mixed_report(), {}))
    for it in q:
        assert it.get("command")
        assert it.get("evidence")
        assert it.get("rank")


def test_queue_is_deterministic():
    m = build_artifact(_mixed_report(), {})
    a = rank_operational_queue(m)
    b = rank_operational_queue(m)
    assert a == b


def test_all_green_fresh_queue_empty():
    m = build_artifact(_report([_res("a", "alpha", "PASS")]), {})
    assert rank_operational_queue(m) == []


# ------------------------------------------------------------------ anti-fabrication

def test_recompute_matches_stored():
    rep = _mixed_report()
    stored = build_artifact(rep, {"run_ts": rep["run_ts"]})
    assert recompute_and_compare(stored, rep)["passed"]


def test_tampered_self_grade_caught():
    rep = _mixed_report()
    stored = build_artifact(rep, {"run_ts": rep["run_ts"]})
    stored["suite"]["pass_rate"] = 1.0          # lie: claim perfect while a domain is BLOCKED
    assert not recompute_and_compare(stored, rep)["passed"]


def test_no_operator_only_states():
    m = build_artifact(_mixed_report(), {})
    assert m["operator_only_states_written"] == []


def test_self_metrics_domain_excluded_from_own_measurement():
    # adding self_metrics validators to the report must NOT change the measured totals/domains
    # (no self-reference), so the artifact stays idempotent run-to-run
    base = _mixed_report()
    with_self = _report(base["results"] + [
        _res("self_metrics_present", "self_metrics", "PASS"),
        _res("self_metrics_derived_from_suite", "self_metrics", "PASS"),
    ], verdict="BLOCKED")
    assert compute_self_metrics(base)["suite"]["total"] == compute_self_metrics(with_self)["suite"]["total"]
    assert "self_metrics" not in compute_self_metrics(with_self)["domains"]


# ------------------------------------------------------------------ ratchet

def test_warn_headroom_within_tightest_ceiling():
    # a warn window wider than the smallest real ceiling (6h) would make every 6h lane always-warn
    assert WARN_HEADROOM_SECONDS <= 6 * 3600
    assert WARN_HEADROOM_SECONDS > 0

import json
from pathlib import Path
import pytest
from dimwit.pipelines import roster_fidelity as rf
from dimwit.pipelines.base import BlockedError


def test_active_targets_cover_14_active_roster():
    targets = rf.active_roster_targets()
    assert len(targets) == 14
    humanoids = [t for t in targets if t["kind"] == "humanoid"]
    mechs = [t for t in targets if t["kind"] == "mech"]
    assert len(humanoids) == 6 and len(mechs) == 8
    keys = {t["key"] for t in targets}
    # quarantined humanoids excluded
    assert "vorlax" not in keys and "ekris" not in keys
    # mechs are rigid, humanoids are smooth
    assert all(t["rigid"] for t in mechs)
    assert all(not t["rigid"] for t in humanoids)


def test_v1_scope_humanoids_certifiable_mechs_deferred():
    cert = rf.certifiable_targets()
    deferred = rf.deferred_targets()
    assert len(cert) == 6 and all(t["kind"] == "humanoid" for t in cert)
    assert len(deferred) == 8 and all(t["kind"] == "mech" for t in deferred)


def test_validate_cert_requires_all_three_legs():
    good = {"asset": "X", "rig": {"passed": True}, "anim": {"passed": True},
            "deformation": {"passed": True, "score": 0.9}}
    assert rf.validate_cert(good)["passed"] is True
    for leg in ("rig", "anim", "deformation"):
        bad = json.loads(json.dumps(good))
        bad[leg]["passed"] = False
        assert rf.validate_cert(bad)["passed"] is False


def test_load_cert_fail_closed(tmp_path):
    with pytest.raises(BlockedError):
        rf.load_cert("SM_Char_Does_Not_Exist", root=tmp_path)


def test_coverage_missing_when_no_certs(tmp_path):
    cov = rf.roster_fidelity_coverage(root=tmp_path)
    assert cov["passed"] is False
    # V1 gate covers the 6 humanoids; the 8 mechs are deferred, not counted as missing
    assert len(cov["missing"]) == 6
    assert len(cov["deferred"]) == 8

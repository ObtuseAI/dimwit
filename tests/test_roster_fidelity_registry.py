from dimwit.pipelines.validation_registry import build_registry


def test_registry_has_roster_fidelity_domain():
    reg = build_registry()
    rf = [v for v in reg if getattr(v, "domain", None) == "character_roster_fidelity"]
    ids = {v.id for v in rf}   # Validator's identifier field is `id`, not `name`
    assert "roster_fidelity_coverage" in ids
    assert "roster_fidelity_mechs_deferred_tracked" in ids
    # V1: 6 humanoid per-char BLOCKER + 1 coverage + 1 mech-deferred tracker
    assert len(rf) == 8, sorted(ids)

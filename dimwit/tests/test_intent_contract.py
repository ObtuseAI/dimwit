"""Proof tests for the per-build INTENT CONTRACT (spec_author.author_intent_contract +
config/intent_contract_schema.json). Stdlib only. Run:  python -m dimwit.tests.test_intent_contract

The contract is the user's law made machine-checkable: "the initial picture/goals/design for any of the
builds is what should be compared against the final capture." These tests lock the doctrine:
  * it is authored UP FRONT and hash-anchored in the ledger BEFORE any pixel can exist (anti-retrofit);
  * a strict asset_type cannot declare intent without a real on-disk reference (vacuous-target block);
  * a declared reference with no license is unusable (provenance fail-closed);
  * the author may only RAISE a frozen floor, never lower it (max(author, frozen));
  * the intent_hash covers only the SCORED rubric, so re-stamping ids/timestamps doesn't move it but
    changing what the capture is judged against does.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit import spec_author
from dimwit.core import Lifecycle
from dimwit.pipelines.validation import resolve_asset_type_floors

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_intent_"))
_SCHEMA = json.loads((Path(spec_author.ROOT) / "config" / "intent_contract_schema.json").read_text("utf-8"))
_REQUIRED_TOP = _SCHEMA["required"]


class _FakeLedger:
    """Minimal stand-in for DimwitLedger: records appended entries and advances a _head hash, which is
    what author_intent_contract reads back as the anchor proof."""
    def __init__(self):
        self.entries = []
        self._head = "0" * 64

    def append(self, entry):
        self.entries.append(entry)
        self._head = spec_author.sha256_obj({"prev": self._head, "entry": entry})
        return self._head


def _ref(name="ref.png", root=None):
    """A real on-disk reference file (content irrelevant at authoring — only existence is checked)."""
    p = (root or _TMP) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\n stub reference pixels")
    return str(p)


def _out():
    """A fresh isolated assets root so each case starts with zero pixels on disk."""
    d = Path(tempfile.mkdtemp(prefix="dimwit_intent_out_", dir=_TMP))
    return d


# ---------------------------------------------------------------------------- happy path

def test_strict_character_happy_path():
    out = _out()
    r = spec_author.author_intent_contract(
        "char_test_01", "character", _ref(),
        declared_intent="dark alien melee enemy, teal spinal Wane vein, single orange chest weak-point",
        provenance={"license_class": "owned_reference", "reference_license": "internal-owned",
                    "source_prompt": "concept sheet"},
        out_root=out)
    assert r["ok"] and not r["blocked"], r
    assert r["state"] == Lifecycle.INTENT_DECLARED, r
    c = r["contract"]
    # schema conformance — every required top-level key is present
    for k in _REQUIRED_TOP:
        assert k in c, f"missing required contract key: {k}"
    # frozen floors applied (author gave none => exactly the character floor)
    fl = resolve_asset_type_floors("character")
    assert c["acceptance"]["confidence_target"] == fl["confidence_floor"] == 0.95, c["acceptance"]
    assert c["acceptance"]["target_match_floor"] == fl["target_match_floor"] == 0.85, c["acceptance"]
    assert c["acceptance"]["require_optics_semantic"] is True, c["acceptance"]
    assert c["acceptance"]["allow_textonly_target"] is False, c["acceptance"]
    # motion stage is mandatory for a strict character
    assert "motion" in c["validation_plan"]["required_capture_stages"], c["validation_plan"]
    # the file was actually written next to where asset_spec would live
    ondisk = json.loads(Path(r["contract_path"]).read_text("utf-8"))
    assert ondisk["intent_hash"] == c["intent_hash"], "written file must match returned contract"
    assert c["review_only"] is True


def test_author_can_only_raise_floor_never_lower():
    out = _out()
    # author tries to LOWER below frozen 0.95 -> clamped UP to 0.95
    low = spec_author.author_intent_contract(
        "char_low", "character", _ref(), confidence_floor=0.80, target_match_floor=0.50,
        provenance={"license_class": "owned_reference", "reference_license": "x", "source_prompt": "p"},
        out_root=out)
    assert low["contract"]["acceptance"]["confidence_target"] == 0.95, "must clamp up to frozen floor"
    assert low["contract"]["acceptance"]["target_match_floor"] == 0.85, "must clamp up to frozen target floor"
    # author RAISES above frozen -> honored
    out2 = _out()
    high = spec_author.author_intent_contract(
        "char_high", "character", _ref(), confidence_floor=0.99, target_match_floor=0.92,
        provenance={"license_class": "owned_reference", "reference_license": "x", "source_prompt": "p"},
        out_root=out2)
    assert high["contract"]["acceptance"]["confidence_target"] == 0.99, high["contract"]["acceptance"]
    assert high["contract"]["acceptance"]["target_match_floor"] == 0.92, high["contract"]["acceptance"]


# ---------------------------------------------------------------------------- fail-closed refusals

def test_anti_retrofit_blocks_when_pixels_exist():
    out = _out()
    base = out / "char_retro"
    base.mkdir(parents=True, exist_ok=True)
    (base / "hero_capture.png").write_bytes(b"already-rendered")
    r = spec_author.author_intent_contract(
        "char_retro", "character", _ref(),
        provenance={"license_class": "owned_reference", "reference_license": "x", "source_prompt": "p"},
        out_root=out)
    assert r["ok"] is False and r["blocked"] is True, r
    assert "already exist" in r["reason"], r
    assert not (base / "intent_contract.json").exists(), "must not write a contract after pixels exist"


def test_vacuous_target_blocks_strict_type():
    out = _out()
    r = spec_author.author_intent_contract(
        "char_notarget", "character", None,           # strict type, NO reference image
        provenance={"license_class": "generated_concept", "source_prompt": "p"},
        out_root=out)
    assert r["ok"] is False and r["blocked"] is True, r
    assert "on-disk target_reference" in r["reason"], r


def test_reference_without_license_blocks():
    out = _out()
    r = spec_author.author_intent_contract(
        "char_nolicense", "character", _ref(),
        provenance={"license_class": "generated_concept", "source_prompt": "p"},  # no reference_license
        out_root=out)
    assert r["ok"] is False and r["blocked"] is True, r
    assert "reference_license" in r["reason"], r


def test_local_override_without_justification_blocks():
    out = _out()
    r = spec_author.author_intent_contract(
        "char_override", "character", _ref(),
        provenance={"license_class": "owned_reference", "reference_license": "x", "source_prompt": "p"},
        local_overrides={"materials.carapace-metallic": {"value": 0.4}},  # no justification
        out_root=out)
    assert r["ok"] is False and r["blocked"] is True, r
    assert "justification" in r["reason"], r
    # with a justification it is allowed
    out2 = _out()
    r2 = spec_author.author_intent_contract(
        "char_override_ok", "character", _ref(),
        provenance={"license_class": "owned_reference", "reference_license": "x", "source_prompt": "p"},
        local_overrides={"materials.carapace-metallic":
                         {"value": 0.4, "justification": "wet-look hero shot, signed off by art lead"}},
        out_root=out2)
    assert r2["ok"] is True, r2


# ---------------------------------------------------------------------------- text-only target (loose type)

def test_textonly_target_allowed_for_loose_prop():
    out = _out()
    fl = resolve_asset_type_floors("prop")
    assert fl["require_optics_semantic"] is False, "prop must be a loose (text-target-allowed) type"
    r = spec_author.author_intent_contract(
        "prop_textonly", "prop", None,                # no reference image
        declared_intent="hex cover crate, teal trim, readable at lane distance",
        provenance={"license_class": "generated_concept", "source_prompt": "p"},
        out_root=out)
    assert r["ok"] is True and r["state"] == Lifecycle.INTENT_DECLARED, r
    assert r["contract"]["acceptance"]["allow_textonly_target"] is True, r["contract"]["acceptance"]
    assert r["contract"]["expected_appearance"]["reference_images"] == [], r["contract"]["expected_appearance"]


# ---------------------------------------------------------------------------- ledger anchoring (anti-retrofit core)

def test_intent_anchored_in_ledger_before_generation():
    out = _out()
    led = _FakeLedger()
    r = spec_author.author_intent_contract(
        "char_anchor", "character", _ref(),
        provenance={"license_class": "owned_reference", "reference_license": "x", "source_prompt": "p"},
        ledger=led, run_id="run-xyz", out_root=out)
    assert r["ok"] and r["anchored"] is True, r
    assert len(led.entries) == 1, "exactly one INTENT_DECLARED entry must be anchored"
    e = led.entries[0]
    assert e["state"] == Lifecycle.INTENT_DECLARED, e
    assert e["candidate_hash"] == "intent:" + r["intent_hash"], e
    assert e["run_id"] == "run-xyz", e
    # the contract records the chain head it was anchored at (proves it predates any later capture entry)
    assert r["contract"]["anchor_entry_hash"] == led._head, r["contract"]


# ---------------------------------------------------------------------------- intent_hash semantics

def test_intent_hash_covers_scored_rubric_only():
    out = _out()
    a = spec_author.author_intent_contract(
        "char_h1", "character", _ref(), authored_ts=111,
        provenance={"license_class": "owned_reference", "reference_license": "x", "source_prompt": "p"},
        out_root=out)["contract"]
    # same scored rubric, different timestamp + id => SAME intent_hash (re-stamping is stable)
    b = dict(a)
    b["authored_ts"] = 999
    b["intent_id"] = "char_h1__different"
    assert spec_author.intent_hash_of(b) == a["intent_hash"], "ids/timestamps must not move the intent_hash"
    # change the actual rubric the capture is judged against => DIFFERENT intent_hash
    c = json.loads(json.dumps(a))
    c["acceptance"]["confidence_target"] = 0.99
    assert spec_author.intent_hash_of(c) != a["intent_hash"], "raising the gate must move the intent_hash"
    d = json.loads(json.dumps(a))
    d["goals"]["summary"] = "a completely different build"
    assert spec_author.intent_hash_of(d) != a["intent_hash"], "changing goals must move the intent_hash"


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, e)); print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, e)); print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())

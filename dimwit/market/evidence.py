"""Evidence export + a tamper-evident ledger for market observations.

`implementation_digest()` is the important function here. DumbMoney's audit found the TA cell was a *costume*:
the runtime stamped `producer: "dimwit"` onto results produced by code Dimwit does not own, and the verifier
checked the stamp it had just written. A name in a field is not provenance. So every export from this module
carries a digest computed over the **actual bytes of the modules that produced it**, which a verifier can
recompute and disagree with.

The ledger fixes the second finding from the same audit. Its chained payload includes `sequence` and
`occurred_at`, and `verify()` checks sequence contiguity as well as the hash chain — so truncating the tail is
detectable, not silent. A ledger whose digest omits its own ordering fields can be shortened without breaking
a single link.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core import sha256_obj
from ..ledger.hashchain import GENESIS, chain_entry, chain_verify
from ..ledger.locking import ledger_lock
from . import bars as bars_mod
from . import indicators as ind
from . import patterns as pat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER_PATH = ROOT / "artifacts" / "market" / "evidence.jsonl"

OBSERVATION_SCHEMA = "dimwit.technical-analysis-observation.v1"
DUMBMONEY_COMPATIBLE_SCHEMA = "dumbmoney.technical-analysis-observation.v2"

#: Deliberately outside the attestation: `cli.py` only parses argv and dispatches into the attested modules, so
#: including it would invalidate every historical digest on a help-text edit. `tests/test_market_cell_contract.py`
#: asserts that ATTESTED_MODULES + NON_ATTESTED_MODULES is exactly the package, so a new module cannot slip in
#: unattested by accident.
NON_ATTESTED_MODULES = ("cli.py",)

#: The modules whose bytes define what "produced by Dimwit" means for market evidence.
ATTESTED_MODULES = (
    "__init__.py",
    "bars.py",
    "chart.py",
    "chart_vision.py",
    "evidence.py",
    "indicators.py",
    "knowledge.py",
    "patterns.py",
    "scan.py",
    "selfaudit.py",
    "sports.py",
)

#: Indicator keys DumbMoney's legacy observation consumers read.
LEGACY_INDICATOR_KEYS = (
    "last_close",
    "sma20",
    "ema12",
    "ema26",
    "macd",
    "rsi14",
    "atr14",
    "sma50",
    "sma200",
    "return20_bps",
    "atr14_percent",
)


class EvidenceError(ValueError):
    """Raised when evidence cannot be produced or verified without weakening its contract."""


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementation_digest() -> dict[str, Any]:
    """Digest over the market cell's own source bytes.

    Returns the per-file digests too, so a mismatch tells a verifier *which* module changed rather than only
    that something did.
    """
    here = Path(__file__).resolve().parent
    files: dict[str, str] = {}
    missing: list[str] = []
    for name in ATTESTED_MODULES:
        target = here / name
        if not target.is_file():
            missing.append(name)
            continue
        files[name] = _file_digest(target)
    if missing:
        raise EvidenceError(f"attested modules missing from the market cell: {missing}")
    return {
        "schema": "dimwit.market-implementation-attestation.v1",
        "cell": "dimwit",
        "package": "dimwit.market",
        "module_count": len(files),
        "modules": dict(sorted(files.items())),
        "digest": sha256_obj(dict(sorted(files.items()))),
        "attests": "these module bytes produced the accompanying observation",
        "does_not_attest": "correctness of the observation, or that any input data is point-in-time",
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def export_dumbmoney_observation(
    series: Mapping[str, Any],
    *,
    chart_render: Mapping[str, Any] | None = None,
    roundtrip: Mapping[str, Any] | None = None,
    include_structure: bool = True,
) -> dict[str, Any]:
    """Build the observation DumbMoney's TA slot consumes, executed by Dimwit for real.

    Field-compatible with `dumbmoney.technical-analysis-observation.v2` (same keys, same units) and a strict
    superset: the full indicator panel, market structure, pattern counts, the implementation attestation, and —
    when a chart was rendered and read back — real `chart_pixel_evidence` instead of `NOT_PROVIDED`.

    Two deliberate honesty details:

    * `rsi14` is Wilder RSI, which is the correct formulation and *not* the flat-average number DumbMoney's
      legacy module emitted under that key. Both are exported and the `parity` block states the difference, so
      the change is visible rather than reconciled behind the same name.
    * `point_in_time_claim` is passed through from the input classification. This function cannot upgrade it.
    """
    normalized = bars_mod.ensure_normalized(series)
    panel = ind.snapshot(normalized)
    legacy_rsi = ind.rsi_simple(bars_mod.closes(normalized))[-1]
    highs = bars_mod.highs(normalized)
    lows = bars_mod.lows(normalized)

    def state_from(rsi_value: float | None) -> str:
        close = panel["last_close"]
        sma20 = panel["sma20"]
        macd_value = panel["macd"]
        if None in (close, sma20, macd_value, rsi_value):
            return "INSUFFICIENT_HISTORY"
        if close > sma20 and macd_value > 0 and rsi_value < 70:
            return "BULLISH_ALIGNMENT"
        if close < sma20 and macd_value < 0 and rsi_value > 30:
            return "BEARISH_ALIGNMENT"
        return "MIXED_OR_EXTENDED"

    indicators_legacy = {key: panel[key] for key in LEGACY_INDICATOR_KEYS if key in panel}
    indicators_legacy["bollinger_upper20"] = panel["bb_upper20"]
    indicators_legacy["bollinger_lower20"] = panel["bb_lower20"]
    indicators_legacy["support20"] = round(min(lows[-20:]), 8) if len(lows) >= 20 else None
    indicators_legacy["resistance20"] = round(max(highs[-20:]), 8) if len(highs) >= 20 else None

    pixel_evidence: Any = "NOT_PROVIDED"
    if chart_render is not None:
        pixel_evidence = {
            "status": "PROVIDED",
            "render_schema": chart_render.get("schema"),
            "plot_digest": chart_render.get("plot_digest") or chart_render.get("svg_sha256"),
            "geometry_price_min": chart_render.get("geometry", {}).get("price_min"),
            "geometry_price_max": chart_render.get("geometry", {}).get("price_max"),
            "bars_rendered": chart_render.get("geometry", {}).get("bars_rendered"),
            "bars_omitted": chart_render.get("geometry", {}).get("bars_omitted"),
        }
        if roundtrip is not None:
            pixel_evidence["roundtrip_verdict"] = roundtrip.get("verdict")
            pixel_evidence["worst_error_px"] = roundtrip.get("worst_error_px")
            pixel_evidence["status"] = (
                "PROVIDED_AND_VERIFIED" if roundtrip.get("verdict") == "PASS" else "PROVIDED_UNVERIFIED"
            )

    observation: dict[str, Any] = {
        "schema": OBSERVATION_SCHEMA,
        "dumbmoney_schema_compatibility": DUMBMONEY_COMPATIBLE_SCHEMA,
        "producer": "dimwit",
        "producer_executed": True,
        "producer_implementation": "dimwit.market",
        "symbol": normalized["symbol"],
        "asset_class": normalized["asset_class"],
        "timeframe": normalized["timeframe"],
        "as_of": normalized["as_of"],
        "source_classification": normalized["classification"],
        "source_schema": normalized.get("source_schema"),
        "source_digest": normalized["digest"],
        "point_in_time_claim": bool(normalized.get("point_in_time_claim", False)),
        "bar_count": normalized["bar_count"],
        "bar_spacing": normalized["spacing"],
        "indicators": indicators_legacy,
        "indicators_full": panel,
        "indicator_family_counts": {
            family: sum(1 for spec in ind.INDICATORS.values() if spec["family"] == family)
            for family in ind.INDICATOR_FAMILIES
        },
        "technical_state": state_from(panel["rsi14"]),
        "parity": {
            "rsi14_wilder": panel["rsi14"],
            "rsi14_simple_legacy": None if legacy_rsi is None else round(legacy_rsi, 8),
            "rsi14_delta": (
                None
                if (panel["rsi14"] is None or legacy_rsi is None)
                else round(panel["rsi14"] - legacy_rsi, 8)
            ),
            "technical_state_legacy_parity": state_from(legacy_rsi),
            "note": (
                "DumbMoney's legacy technical_analysis._rsi averages the trailing window flat; this cell uses "
                "Wilder smoothing. Both are reported so the change is auditable, not silent."
            ),
        },
        "chart_pixel_evidence": pixel_evidence,
        "candidate_status": (
            "RESEARCH_INPUT_ONLY"
            if normalized["classification"] == "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE"
            else "WALK_FORWARD_EVIDENCE_REQUIRED"
        ),
        "forecast_probability": None,
        "expected_return_bps": None,
        "broker_credentials_available": False,
        "broker_calls": 0,
        "orders_created": 0,
        "live_activation": False,
        "execution_authority": False,
        "recommendation_only": True,
        "implementation_attestation": implementation_digest(),
    }

    if include_structure:
        structure = pat.market_structure(normalized)
        detections = pat.detect_patterns(normalized)
        observation["market_structure"] = structure
        observation["support_resistance"] = pat.support_resistance(normalized)
        observation["patterns"] = {
            "pattern_family_size": detections["pattern_family_size"],
            "detection_count": detections["detection_count"],
            "counts_by_pattern": detections["counts_by_pattern"],
            "confirmation_lag_bars": detections["confirmation_lag_bars"],
            "most_recent": detections["detections"][-3:],
        }

    observation["digest"] = sha256_obj(
        {key: value for key, value in observation.items() if key != "digest"}
    )
    return observation


class MarketEvidenceLedger:
    """Append-only, hash-chained JSONL ledger for market observations.

    A hash chain alone cannot detect **tail truncation**: drop the last N lines and every remaining link still
    verifies, and the sequence numbers still run 0..k with no gap. Detecting it requires a commitment to the
    expected length made *outside* the file being checked. This class keeps two:

    * a local `<ledger>.head.json` anchor written on every append, which catches truncation by anything that
      edits the ledger without also updating the anchor;
    * optional `expected_head` / `expected_count` arguments to `verify()`, for a caller holding the commitment
      somewhere the ledger's writer cannot reach.

    The local anchor is explicitly **not** independent — anything with write access to both files can forge a
    consistent pair — and `verify()` reports that rather than implying otherwise.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_LEDGER_PATH
        self.anchor_path = self.path.with_name(self.path.name + ".head.json")

    # -- reading ---------------------------------------------------------
    def entries(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        out: list[dict[str, Any]] = []
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                out.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"{self.path}:{line_number} is not valid JSON: {exc}") from exc
        return out

    def head(self) -> str:
        rows = self.entries()
        return str(rows[-1]["entry_hash"]) if rows else GENESIS

    def anchor(self) -> dict[str, Any] | None:
        """The recorded length/head commitment, or None if no anchor has been written."""
        if not self.anchor_path.is_file():
            return None
        try:
            return json.loads(self.anchor_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"{self.anchor_path} is not valid JSON: {exc}") from exc

    def _write_anchor(self, count: int, head: str, occurred_at: str) -> None:
        payload = {
            "schema": "dimwit.market-evidence-anchor.v1",
            "ledger": self.path.name,
            "entry_count": count,
            "head": head,
            "updated_at": occurred_at,
            "independent": False,
            "note": "Local anchor: detects truncation by a writer that misses this file. Not a trusted signer.",
        }
        temporary = self.anchor_path.with_suffix(self.anchor_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        temporary.replace(self.anchor_path)

    # -- writing ---------------------------------------------------------
    def append(
        self,
        observation: Mapping[str, Any],
        *,
        kind: str = "observation",
        occurred_at: str | None = None,
        actor: str = "dimwit.market",
    ) -> dict[str, Any]:
        """Chain and append one record. Returns the stored entry."""
        if not isinstance(observation, Mapping) or not observation:
            raise EvidenceError("observation must be a non-empty object")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_lock(self.path):
            rows = self.entries()
            entry = {
                "sequence": len(rows),
                "kind": str(kind),
                "actor": actor,
                "occurred_at": occurred_at or _utc_now(),
                "observation_schema": observation.get("schema"),
                "observation_digest": observation.get("digest") or sha256_obj(observation),
                "observation": dict(observation),
            }
            chained = chain_entry(entry, rows[-1]["entry_hash"] if rows else GENESIS)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(chained, sort_keys=True, default=str) + "\n")
            self._write_anchor(len(rows) + 1, str(chained["entry_hash"]), str(entry["occurred_at"]))
        return chained

    # -- verification ----------------------------------------------------
    def verify(
        self,
        *,
        expected_head: str | None = None,
        expected_count: int | None = None,
    ) -> dict[str, Any]:
        """Chain, ordering and length verification.

        Pass `expected_head`/`expected_count` when the caller holds the commitment externally — that is the only
        form of truncation detection that does not depend on a file the ledger's own writer controls.
        """
        rows = self.entries()
        chain = chain_verify(rows)
        expected = list(range(len(rows)))
        actual = [row.get("sequence") for row in rows]
        contiguous = actual == expected
        digest_mismatches = [
            row.get("sequence")
            for row in rows
            if row.get("observation_digest")
            and row.get("observation", {}).get("digest")
            and row["observation_digest"] != row["observation"]["digest"]
        ]
        head = self.head()
        anchor = self.anchor()
        anchor_report: dict[str, Any] = {
            "present": anchor is not None,
            "independent": False,
            "matches": None,
            "recorded_entry_count": None if anchor is None else anchor.get("entry_count"),
            "recorded_head": None if anchor is None else anchor.get("head"),
        }
        if anchor is not None:
            anchor_report["matches"] = (
                anchor.get("entry_count") == len(rows) and anchor.get("head") == head
            )
        external_report: dict[str, Any] = {"supplied": False, "matches": None}
        if expected_head is not None or expected_count is not None:
            external_report["supplied"] = True
            external_report["matches"] = (
                expected_head in (None, head) and expected_count in (None, len(rows))
            )
            external_report["expected_head"] = expected_head
            external_report["expected_count"] = expected_count

        truncation_detectable = anchor_report["present"] or external_report["supplied"]
        ok = (
            bool(chain.get("ok"))
            and contiguous
            and not digest_mismatches
            and anchor_report["matches"] is not False
            and external_report["matches"] is not False
        )
        return {
            "schema": "dimwit.market-evidence-verification.v1",
            "producer": "dimwit",
            "path": str(self.path),
            "entry_count": len(rows),
            "head": head,
            "chain": chain,
            "sequence_contiguous": contiguous,
            "expected_sequence_head": len(rows) - 1 if rows else None,
            "observation_digest_mismatches": digest_mismatches,
            "length_anchor": anchor_report,
            "external_commitment": external_report,
            "truncation_detectable": truncation_detectable,
            "ok": ok,
            "detects": [
                "edit of any past entry (hash chain)",
                "removal or re-chaining of a middle entry (hash chain)",
                "swap of an observation body under a recorded digest",
                "tail truncation, ONLY via the length anchor or a supplied external commitment",
            ],
            "does_not_detect": (
                []
                if truncation_detectable
                else ["tail truncation: no length anchor and no external commitment was supplied"]
            )
            + ["forgery by an actor able to rewrite both the ledger and its local anchor"],
        }

    def summary(self) -> dict[str, Any]:
        rows = self.entries()
        by_kind: dict[str, int] = {}
        by_schema: dict[str, int] = {}
        for row in rows:
            by_kind[str(row.get("kind"))] = by_kind.get(str(row.get("kind")), 0) + 1
            by_schema[str(row.get("observation_schema"))] = (
                by_schema.get(str(row.get("observation_schema")), 0) + 1
            )
        return {
            "schema": "dimwit.market-evidence-summary.v1",
            "producer": "dimwit",
            "path": str(self.path),
            "entry_count": len(rows),
            "head": self.head(),
            "by_kind": dict(sorted(by_kind.items())),
            "by_observation_schema": dict(sorted(by_schema.items())),
            "first_occurred_at": rows[0]["occurred_at"] if rows else None,
            "last_occurred_at": rows[-1]["occurred_at"] if rows else None,
        }


def record_observations(
    observations: Sequence[Mapping[str, Any]],
    *,
    path: str | Path | None = None,
    kind: str = "observation",
) -> dict[str, Any]:
    """Append several observations and return the post-append verification. Convenience for the capability
    registry, which dispatches by name with plain kwargs."""
    ledger = MarketEvidenceLedger(path)
    stored = [ledger.append(item, kind=kind)["entry_hash"] for item in observations]
    verification = ledger.verify()
    verification["appended"] = len(stored)
    verification["appended_hashes"] = stored
    return verification

# Dimwit as DumbMoney's market cell (`dimwit.market`)

## Why this exists

DumbMoney's `contracts/runtime-bindings.v1.json` assigns Dimwit the runtime role
`chart_vision_and_deterministic_technical_analysis_for_stocks_and_crypto`. Its own binding was honest about what
that meant in practice:

```json
"implementation_status": "PARTIAL",
"limitations": [
  "deterministic_ohlcv_indicators_plus_held_out_ta_evidence",
  "chart_pixels_and_visual_perception_not_implemented",
  "frozen_dimwit_is_a_game_production_studio_and_is_not_executed"
]
```

The technical analysis lived in `DumbMoney/src/dumbmoney/technical_analysis.py`, produced a result stamped
`producer: "dimwit"`, and Dimwit contributed nothing to it. Dimwit's own tree — 368 Python files, ~57k lines —
contained **zero** market code: the word "chart" appeared once, in the README.

`dimwit.market` closes that gap with code that really runs, and `dimwit market audit` reports the honest
manifest so the costume cannot come back quietly.

## Doctrine

Inherited unchanged from the studio side, because these are the rules that make the studio's evidence worth
anything:

| Rule | How it is enforced |
|---|---|
| Observations, never forecasts | Every result carries `forecast_probability: None`; a test asserts it across all 15 public result types |
| Fail closed | Missing or ambiguous evidence returns `BLOCKED`; there is no default pass |
| No lookahead | Indicators are prefix-stable, proven per indicator by recomputation on truncated prefixes |
| Disclose the search | `family_size`, Bonferroni and Benjamini–Hochberg on every scan |
| No network, no credentials, no broker | A test greps the modules for network imports |
| Provenance is recomputable | Every export carries a digest of the module bytes that produced it |

## What is in it

| Module | Responsibility |
|---|---|
| `bars.py` | The single input gate: validation, canonicalization, point-in-time prefixes, timeframe resampling |
| `indicators.py` | 46 prefix-stable indicators across 7 families, with exact warmup accounting |
| `patterns.py` | 24 candlestick / structure / divergence detectors, each carrying its confirmation lag |
| `chart.py` | Deterministic candlestick renderer (PNG + SVG, 3 themes) with invertible geometry |
| `chart_vision.py` | Reads price structure back out of pixels; the declared "not implemented" limitation |
| `scan.py` | Walk-forward rule scanner over 35 rules: the settled-observation factory |
| `sports.py` | Game-state analysis, margin/win-probability charting, cross-game rule scanner |
| `knowledge.py` | 111 citable terms merged from the code registries plus a 41-concept pack |
| `evidence.py` | DumbMoney-compatible export, implementation attestation, hash-chained ledger |
| `selfaudit.py` | Runs the whole cell and reports what actually executed (the anti-costume gate) |
| `cli.py` | `python -m dimwit market <cmd>` — each command exits non-zero on BLOCKED |

## The three ideas that matter

### 1. Prefix stability is the no-lookahead proof

An indicator is prefix-stable when

```
indicator(bars)[i] == indicator(bars[:i+1])[-1]
```

`tests/test_market_indicators.py` recomputes all 46 indicators on truncated prefixes and requires bar-for-bar
agreement. That converts "no lookahead" from an assurance into a property a test can fail. The same test pins
each indicator's first-defined index against its registry `warmup_bars`, so a "20-period SMA" can never be
quietly computed from six bars.

Patterns get the same treatment through a different mechanism. A fractal swing high at bar 40 with two right
bars is not knowable until bar 42, so every detection carries **both** `index` (where it is) and
`detected_at_index` (when it became knowable). Rules only ever read `detected_at_index`.

### 2. Chart vision is falsifiable or it is nothing

`render_chart_png` returns the exact pixel geometry it used. `read_chart` inverts it. `verify_chart_roundtrip`
does both against a series whose values are known and reports the recovery error **in pixels** — currently
≤ 0.5 px on all four OHLC fields, with zero direction mismatches, across every theme and window size.

Foreign screenshots are the harder case and are handled honestly: `describe_chart` reports shape only (bar
count, up/down mass, pixel-space slope, congestion) and pins `price_scale: "UNKNOWN"`. Without an axis mapping
there is no honest way to name a price, so it never does.

Two bugs found and fixed while building this, both of the "silently plausible wrong answer" kind:

* a saturated background (Dimwit's own `tote` theme is pitch green) was read as one enormous up candle — fixed
  by excluding large flat fills by exact color;
* theme gridlines whose hue matches a candle merged every bar into one blob — fixed by excluding colors that
  draw horizontal runs wider than half the frame, which no candle can.

### 3. Settled observations are the scarce resource

Rules are free. Trustworthy outcomes to judge them against are not. `scan.py` is therefore built to *count
honestly* rather than to find things:

* **Walk-forward with embargo.** `warmup → training → embargo → holdout`. Selection uses training only.
* **Explicit execution model.** Signal at bar *i* → entry at bar *i+1* **open** → exit `horizon` bars later at
  the close, minus a round-trip cost. Never a fill at the signal bar.
* **Tested against a baseline, not zero.** Each rule is scored on its **excess** over the unconditional
  same-side return of the segment. Without this, a long rule "wins" any rising segment and no statistical
  correction notices.
* **Overlap deflation.** Overlapping fixed-horizon windows are not independent draws; every t-statistic is also
  reported deflated by `sqrt(horizon)`, and survivor accounting uses the deflated one.
* **Search disclosure.** `family_size` plus Bonferroni and Benjamini–Hochberg survivors.
* **A placebo.** `placebo_control` re-runs everything with every entry displaced by a fixed bar lag, then
  reports the comparison: a real result at or below its own placebo is `NOT_DISTINGUISHABLE_FROM_PLACEBO`.

Verified behaviour: on a driftless random walk the scan yields **zero** survivors and is not distinguishable
from its placebo. On a series with a rare *conditional* edge injected, the responsible rule is recovered with
+345 bps excess while the placebo yields zero. Power and discipline, both tested.

Sports is the cheaper source of the same resource, and the module says why: distinct games do not share outcome
windows, so one settled game is one independent draw per rule and **no overlap deflation is applied or needed**.
Hit rates there are benchmarked against a fair coin and stamped `FAIR_COIN_NOT_MARKET_PRICE` — beating 50% is
not an edge, beating the price is, and no prices are present.

## Provenance: the anti-costume mechanism

`evidence.implementation_digest()` hashes the **actual bytes** of the eleven attested market modules and returns
both the combined digest and the per-file map, so a mismatch names the module that moved. Every export embeds
it. That is the difference between "this came from Dimwit" as a label and as something a verifier can recompute
and disagree with.

`tests/test_market_cell_contract.py` asserts that every `.py` file in the package is either attested or
explicitly exempt (`cli.py` only, because it just parses argv), so a new module cannot slip in unattested.

The evidence ledger is hash-chained, and its chained payload includes `sequence` and `occurred_at`. A hash chain
alone cannot detect **tail truncation** — drop the last N lines and every remaining link still verifies — so a
`<ledger>.head.json` length anchor is written on every append, and `verify()` also accepts an external
`expected_head`/`expected_count`. The verification result lists what it detects *and* what it does not: the
local anchor is not an independent signer, and anything that can rewrite both files can forge a consistent pair.

Tamper matrix, all tested:

| Attack | Detected by |
|---|---|
| Edit a past entry | Hash chain |
| Remove or re-chain a middle entry | Hash chain |
| Swap an observation body under its recorded digest | Chain + digest cross-check |
| Truncate the tail | Length anchor, or a supplied external commitment — **nothing**, without one |

## Using it

```bash
python -m dimwit market audit --deep
python -m dimwit market indicators --self
python -m dimwit market patterns --self
python -m dimwit market analyze --self
python -m dimwit market chart --self --bars 140 --theme tote --out today
python -m dimwit market vision --self --bars 120
python -m dimwit market scan --self --null
python -m dimwit market know adverse_selection
python -m dimwit market know --search fee
python -m dimwit market ledger
```

Every command prints one JSON document and exits non-zero on a BLOCKED verdict, so each is usable directly as a
shell gate. `--self` runs against the deterministic synthetic fixture; otherwise pass a `series.json`.

## Capabilities and MCP

26 capabilities are registered in `config/capability_registry.json` (registry total 52, all resolving):

* 24 under the new **`MARKET`** domain — pure read-only analysis, no network, no writes. `MARKET` is in
  `agent_loop._SAFE_DOMAINS`, so the brain agent loop can reach them, and it is *not* in the MCP server's
  `MUTATING_DOMAINS`, so they dispatch without the mutation opt-in.
* 2 under **`EXECUTE`** — `chart.export` and `evidence.record` write files, so they stay behind
  `DIMWIT_MCP_ALLOW_MUTATION`. A test asserts neither is registered as a `MARKET` capability.

One gate was **added**, none relaxed: `MARKET/chart.read` and `MARKET/chart.describe_foreign` accept a local
image path, so the MCP server confines that argument to the approved capture roots. Nothing leaves the machine,
but an unconfined path over MCP is still an arbitrary-file-read primitive.

## Feeding DumbMoney

`evidence.export_dumbmoney_observation(series, chart_render=..., roundtrip=...)` emits
`dimwit.technical-analysis-observation.v1`, field-compatible with
`dumbmoney.technical-analysis-observation.v2` and a strict superset: full indicator panel, market structure,
support/resistance, pattern counts, the implementation attestation, and real `chart_pixel_evidence`
(`PROVIDED_AND_VERIFIED` with a pixel error, instead of `NOT_PROVIDED`).

One field changes meaning, disclosed rather than reconciled: `rsi14` is now **Wilder** RSI, not the
flat-average number DumbMoney's legacy `_rsi` produced under the same key. Both values, their delta, and both
resulting `technical_state` labels ship in a `parity` block. `point_in_time_claim` is passed through from the
input classification — this function cannot upgrade it, and a retrospective backfill can never claim it.

## What this cell deliberately does not do

Reported by `audit_market_cell()` under `honest_limitations`:

* **No forecast probabilities or expected returns.** Observations only; probability claims are doofus's after
  held-out evidence.
* **No live market data.** No network. Bars arrive from the caller with a declared classification.
* **No order routing or brokerage access.** Kalshi belongs to dummy, Robinhood to dopey. This cell holds no
  credentials.
* **No win-probability model.** A supplied curve is analyzed and attributed to the caller; absent one, the
  result says `NOT_PROVIDED`.
* **No prices from foreign chart images.** Shape only.

## Test coverage

239 tests in `dimwit/tests/test_market_*.py`, all passing. The wider suite goes from 655 to 894 passing with
no new failures; the 39 pre-existing failures all require the UE project and Blender, which this checkout does
not have.

| File | Tests | Load-bearing assertion |
|---|---|---|
| `test_market_bars.py` | 25 | Every dishonest series shape raises; a raw payload cannot bluff past the gate |
| `test_market_indicators.py` | 18 | All 46 indicators prefix-stable; warmup registry exact |
| `test_market_patterns.py` | 22 | Hand-built shapes detected; `detected_at_index` never precedes knowability |
| `test_market_chart.py` | 22 | Byte determinism, geometry invertibility, export path confinement |
| `test_market_chart_vision.py` | 17 | Sub-pixel round-trip; BLOCKED rather than guessed; themed backgrounds |
| `test_market_scan.py` | 31 | Execution model, baseline excess, power *and* discipline |
| `test_market_sports.py` | 36 | Independence claim holds; win probability never invented |
| `test_market_knowledge.py` | 14 | Code is the source of truth; unknown terms raise |
| `test_market_evidence.py` | 27 | Attestation from real bytes; full tamper matrix |
| `test_market_cell_contract.py` | 27 | The anti-costume contract, end to end |

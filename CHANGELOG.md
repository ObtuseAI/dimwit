# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `dimwit.market`: the market evidence lane — the studio's evidence law applied to prices and game state
  instead of pixels and packages, with the same fail-closed discipline.
  - 46 prefix-stable indicators and 24 pattern detectors, each carrying its confirmation lag.
  - Deterministic candlestick renderer (PNG + SVG, three themes) with invertible pixel geometry, plus chart
    vision that reads the prices back out and reports recovery error in pixels.
  - Walk-forward rule scanner over 35 rules with baseline-excess scoring, overlap deflation, Bonferroni and
    Benjamini–Hochberg search disclosure, and a placebo control.
  - Sports game-state analysis, margin/win-probability charting, and a cross-game rule scanner whose
    observations are genuinely independent.
  - A 111-term citable knowledge pack merged from the code registries plus 41 methodology, microstructure and
    assurance concepts.
  - Downstream-compatible observation export, an implementation attestation over the market modules' own bytes,
    and a hash-chained evidence ledger with a length anchor so tail truncation is detectable.
  - `python -m dimwit market <cmd>` operator surface; each command exits non-zero on a BLOCKED verdict.
  - `dimwit market audit` — the anti-costume gate: runs the cell and reports what actually executed.
- New `MARKET` capability domain (24 read-only capabilities). The two writing verbs, `EXECUTE/chart.export` and
  `EXECUTE/evidence.record`, stay behind the existing MCP mutation gate.
- MCP path confinement for the chart-vision verbs that accept a local image path.
- 239 tests in `dimwit/tests/test_market_*.py`.

## [0.1.1] - 2026-07-26

### Fixed

- Replaced the stale pre-Dimwit studio capture with a fresh, source-backed
  Dimwit Studio screenshot.
- Corrected the live studio reactor monogram and removed the retired product name
  from public documentation and ledger descriptions.
- Added a fail-closed public-release check for stale branding and Dimwit UI identity.

## [0.1.0] - 2026-07-26

### Added

- First public source preview of the proof-gated multi-DCC production registry,
  review-oriented studio surface, validation ledger, and promotion pipeline.
- A visual project guide with toolchain, evidence, and promotion-state diagrams.
- Public security, contribution, citation, and release-readiness contracts.

### Changed

- Sanitized workstation-specific paths while keeping toolchain configuration explicit.
- Renamed character asset-token fields to asset identifiers and mech keys to character
  identifiers so repository secret scanning reflects their actual semantics.
- Clarified that GitHub publication requires an explicit owner release instruction.

## Scope

This release exposes the orchestration and evidence system. It does not include licensed
DCC applications, Unreal Engine content, private media assets, or a turnkey production bundle.

[Unreleased]: https://github.com/ObtuseAI/dimwit/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/ObtuseAI/dimwit/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ObtuseAI/dimwit/releases/tag/v0.1.0

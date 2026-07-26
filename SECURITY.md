# Security policy

Dimwit is a public source-available research preview under active hardening.

## Reporting a vulnerability

Use this repository's **Security** tab and **Report a vulnerability** to open a
private GitHub security advisory. Do not open a public issue containing
credentials, private game assets, workstation paths, proof captures, exploit
details, or engine/store account information.

Include the affected revision, component, preconditions, source-to-sink path,
impact, and a minimal non-destructive reproducer. Good-faith, authorized
research that respects the license, avoids privacy violations and service
disruption, and gives the maintainers reasonable remediation time is welcome.

## Supported versions

Only the current default branch and latest tagged public preview are supported.
Historical private-archive commits, generated handoff packages, and
workstation-specific production records are not supported releases.

## Deployment assumptions

- Run Dimwit as a non-administrator where practical.
- Keep the Studio IDE and Unreal bridge bound to loopback.
- Use a random `DIMWIT_UE_BRIDGE_TOKEN` of at least 32 characters and never
  commit it.
- Keep mutation and paid-provider opt-ins disabled except for intentionally
  reviewed operations.
- Treat model output, downloaded models, engine plugins, project scripts, and
  imported assets as untrusted.
- Review plans, resolved paths, executable identities, costs, licenses,
  provenance, and proof destinations before live execution.
- Never treat `PROMOTED_TO_REVIEW` as human acceptance, publishing approval,
  signing approval, payment approval, or active-slice promotion.

## Security invariants

- Missing or stale evidence fails closed.
- Provider output is data, never implicit executable authority.
- Generic capability selection cannot expand an allowlist.
- Filesystem writes remain inside approved roots.
- Live Unreal messages require authentication; generic inspection is read-only.
- Autonomous workflows stop at `PROMOTED_TO_REVIEW`.

## Release hygiene

Public releases require clean current-tree and history secret scans, no personal
or private-share paths, dependency/submodule/license/provenance review,
clean-clone tests, read-only workflow permissions, and exact-SHA GitHub proof.

# Quality Tooling Refresh

## Approved Scope

Refresh supported dependencies and existing quality tooling.
Preserve public APIs, generated artifacts and repository-specific boundaries.

## Acceptance

- Pinact remains locked to `4.1.1` with `lint` and `upgrade`.
- The full no-fix Trunk scan and declared project gates pass.
- Changed manifests have package-manager-generated lockfiles under repository policy.
- Advisory dispositions have specific evidence and affected knowledge claims are reconciled.

## Publication

Push and PR creation require explicit repository-specific approval.
After approval, continue the requested hosted gates, merge, cleanup and memory recording.

## Filesystem Reader Follow-up

Use the reviewed standard-library filesystem reader and 17 regressions from `receipt-scraper/.trunk/configs/`.
Add its project-relative path to Trunk's `direct_configs` so the copy sandbox contains the reader.
Retain decoded results at file level when no literal position is available, omit secret values from messages and reject malformed conversion without partial clean output.
Run the exact test file in CI without changing the existing application or plugin commands.
Preserve public contracts, product source, manifests, locks, workflows that publish output, runtime pins, hook policies and exclusions.

## Confirmed fixture exception

The operator confirmed both credential-shaped constants in `plugins/guard-hooks/hooks/output-secret-mask.test.py` were never issued.
Exclude only that exact file from TruffleHog, without reading or changing its protected values.
This suppresses every TruffleHog finding in that file, not just the two fixtures.
Other linters and other scanner targets remain active; literal and decoded positive controls must run outside the exception.

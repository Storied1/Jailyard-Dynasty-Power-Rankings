# 2026 Prospective Pipeline (P-lane)

> Moved out of CLAUDE.md 2026-08-20 (size cap). Rules here are LAW for any P-lane work.

Contract: `docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md`.
Modules: `scripts/{capture,capture_optional,cutoff,bundle,seal}_2026.py`.

```bash
export POLARS_SKIP_CPU_CHECK=1   # required for the nflreadpy path
python scripts/capture_2026.py --season 2026 --tranche A
python scripts/capture_2026.py --season 2026 --component <id>
python scripts/cutoff_2026.py --season 2026 --write-receipt
python scripts/bundle_2026.py --edition <ed> --arm record_points --policy content/governance/source_policy_2026.v1.json
python scripts/seal_2026.py --edition <ed> --arm record_points --trial 1
python scripts/seal_2026.py --verify-all     # and --rederive-all
```

- **Append-only store** — `data/captures/2026/`, `content/seals/2026/` are
  never edited, deleted, or re-sealed; exclusive-create enforces it.
- **`source_policy_2026.v1.json` is FROZEN** — supersede only via a new
  version; freezing requires `--expected-candidate-sha256`.
- **Prospective label** = ended AND sealed ≤ cutoff, read only from the
  hash-verified cutoff receipt; no reclassification mechanism exists.
- **Locators are repo-relative POSIX**; the seals tree is TRACKED;
  `private_captures/` + `private_bundles/` are gitignored — never `git add -f`.
- **Staging guard before committing captures/bundles:**
  `git diff --cached --name-only | grep -qE '^(private_captures|private_bundles)/'`
  must match nothing.
- **New scripts bootstrap BOTH paths** — `scripts/` AND the repo root.

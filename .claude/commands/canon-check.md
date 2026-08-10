# Canon Check (week ${WEEK})

Pre-render gate: is the underlying data in shape, and is the edition
consistent with everything published before it?

## Step 1: artifacts (always)

```bash
python scripts/canon_checks.py --week ${WEEK}   # or --preseason
```

Validates the sanitized chat context shape and the packet's as-of-week
standings fields. FAIL stops here; fix the generator, never the content.

## Step 2: content (if written)

```bash
python scripts/verify_week_content.py --week ${WEEK} --pretty
```

Then read the edition's callbacks and `meta.threads` against the published
editions that precede it: every callback must match what was actually
published. Verdict PASS or FAIL; anything wrong is FAIL.

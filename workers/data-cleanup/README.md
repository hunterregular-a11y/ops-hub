# Data Cleanup & Structured Report Worker v1

A deliberately narrow deterministic worker for repeatable tabular cleanup. It is designed to reduce manual spreadsheet/CSV cleanup without making semantic guesses.

## What v1 does

- Reads `.csv` and `.xlsx` files without modifying the source.
- Applies explicit normalization rules only: Unicode NFKC, whitespace handling, configured blank tokens, lower/upper casing, and digits-only fields.
- Performs exact or exact-key deduplication. No fuzzy matching. Blank or validation-invalid dedupe keys are never auto-removed.
- Validates required, email, and regex rules.
- Keeps the first exact duplicate and copies removed duplicates into the exceptions file with the original source-row reference.
- Keeps validation-failing nonduplicate rows in the cleaned output while also copying them into exceptions for review. This prevents silent data loss.
- Writes a cleaned dataset, exceptions CSV, JSON audit report, and Markdown run report.
- Refuses to overwrite prior generated outputs unless `--overwrite` is explicitly supplied.
- Reports filenames rather than local absolute paths, avoiding accidental path disclosure when reports are shared.

## Safety contract

1. Source inputs are read-only.
2. No AI/model calls are used.
3. No fuzzy merge or inferred correction is permitted in v1.
4. Any ambiguous/invalid record is surfaced for review rather than guessed at.
5. Each report records the source SHA-256 and exact configuration used.

## Run

```bash
cd workers/data-cleanup
python -m pip install -r requirements.txt
python cleanup.py input.csv --config example-config.json --output-dir output
```

The same command accepts `.xlsx` input. By default, the first worksheet is used; set `input.sheet` in config to name a worksheet explicitly.

## Outputs

For `contacts.csv`, v1 creates:

- `contacts.cleaned.csv` (or `.xlsx` when source is XLSX)
- `contacts.exceptions.csv`
- `contacts.report.json`
- `contacts.report.md`

The report contains row counts, exact duplicates removed, exception counts, validation counts, normalization counts, runtime, source hash, and the effective config.

## Proof metrics before expansion

Measure these on real work before adding features or agents:

- manual minutes avoided;
- rows processed;
- exception/review rate;
- any incorrect deterministic change;
- number of genuine reuses;
- revenue directly enabled.

If a repeated need cannot be expressed safely as an explicit deterministic rule, leave it for human/main-assistant review until there is enough evidence for a separate narrow judgment worker.

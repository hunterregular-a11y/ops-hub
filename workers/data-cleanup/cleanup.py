#!/usr/bin/env python3
"""Deterministic CSV/XLSX cleanup worker. Source files are never modified."""
from __future__ import annotations

import argparse, csv, hashlib, json, re, sys, time, unicodedata
from collections import Counter
from pathlib import Path

try:
    from openpyxl import Workbook, load_workbook
except ImportError:
    Workbook = load_workbook = None

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DEFAULT = {
    "headers": {"mode": "preserve"},
    "normalization": {
        "trim_whitespace": True,
        "collapse_internal_whitespace": False,
        "unicode_nfkc": True,
        "blank_tokens": [""],
        "columns": {},
    },
    "dedupe": {"enabled": False, "keys": [], "case_sensitive": False},
    "validation": {"columns": {}},
}


class CleanupError(Exception):
    pass


def merge(base, supplied):
    out = dict(base)
    for key, value in supplied.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def config_from(path):
    if path is None:
        return DEFAULT
    try:
        supplied = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CleanupError(f"Cannot read config: {exc}") from exc
    if not isinstance(supplied, dict):
        raise CleanupError("Config root must be a JSON object")
    return merge(DEFAULT, supplied)


def snake(value):
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"_+", "_", re.sub(r"[^\w]+", "_", value)).strip("_").lower() or "column"


def headers_for(values, mode):
    if mode not in {"preserve", "snake_case"}:
        raise CleanupError(f"Unsupported headers.mode: {mode}")
    names = [str(v or "").strip() if mode == "preserve" else snake(v) for v in values]
    seen, result = Counter(), []
    for index, name in enumerate(names, 1):
        name = name or f"column_{index}"
        seen[name] += 1
        result.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return result


def read_input(path, cfg):
    mode = cfg["headers"]["mode"]
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(8192); handle.seek(0)
            try: dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
            except csv.Error: dialect = csv.excel
            reader = csv.reader(handle, dialect)
            try: headers = headers_for(next(reader), mode)
            except StopIteration: raise CleanupError("Input CSV is empty")
            rows, source_rows = [], []
            for number, values in enumerate(reader, 2):
                if len(values) > len(headers):
                    raise CleanupError(f"Row {number} has more cells than the header")
                values += [""] * (len(headers) - len(values))
                rows.append(dict(zip(headers, [str(v or "") for v in values]))); source_rows.append(number)
            return headers, rows, source_rows, "csv", None
    if path.suffix.lower() == ".xlsx":
        if load_workbook is None:
            raise CleanupError("XLSX support requires openpyxl")
        wb = load_workbook(path, read_only=True, data_only=True)
        wanted = cfg.get("input", {}).get("sheet")
        if wanted and wanted not in wb.sheetnames:
            raise CleanupError(f"Worksheet not found: {wanted}")
        ws = wb[wanted] if wanted else wb[wb.sheetnames[0]]
        iterator = ws.iter_rows(values_only=True)
        try: headers = headers_for(next(iterator), mode)
        except StopIteration: raise CleanupError("Input XLSX sheet is empty")
        rows, source_rows = [], []
        for number, values in enumerate(iterator, 2):
            values = list(values)
            if len(values) > len(headers) and any(v not in (None, "") for v in values[len(headers):]):
                raise CleanupError(f"Row {number} has data beyond the header")
            values = values[:len(headers)] + [None] * max(0, len(headers) - len(values))
            rows.append(dict(zip(headers, ["" if v is None else str(v) for v in values]))); source_rows.append(number)
        return headers, rows, source_rows, "xlsx", ws.title
    raise CleanupError("Supported inputs are .csv and .xlsx")


def normalize(value, global_cfg, column_cfg):
    result, changes = value, []
    if global_cfg.get("unicode_nfkc", True):
        new = unicodedata.normalize("NFKC", result)
        if new != result: changes.append("unicode_nfkc"); result = new
    if global_cfg.get("trim_whitespace", True):
        new = result.strip()
        if new != result: changes.append("trim_whitespace"); result = new
    if global_cfg.get("collapse_internal_whitespace", False):
        new = re.sub(r"\s+", " ", result)
        if new != result: changes.append("collapse_internal_whitespace"); result = new
    blanks = {str(v).casefold() for v in global_cfg.get("blank_tokens", [""])}
    if result and result.casefold() in blanks:
        changes.append("blank_token"); result = ""
    for op in column_cfg.get("normalizers", []):
        if op == "lowercase": new = result.lower()
        elif op == "uppercase": new = result.upper()
        elif op == "digits_only": new = re.sub(r"\D", "", result)
        else: raise CleanupError(f"Unsupported normalizer: {op}")
        if new != result: changes.append(op); result = new
    return result, changes


def validate(column, value, rules):
    if rules.get("required") and not value:
        return [f"{column}:required"]
    if not value:
        return []
    issues = []
    if rules.get("type") == "email" and not EMAIL.fullmatch(value):
        issues.append(f"{column}:invalid_email")
    elif rules.get("type") not in (None, "email"):
        raise CleanupError(f"Unsupported validation type for {column}")
    if "regex" in rules:
        try: matched = re.fullmatch(rules["regex"], value)
        except re.error as exc: raise CleanupError(f"Invalid regex for {column}: {exc}") from exc
        if not matched: issues.append(f"{column}:regex_mismatch")
    return issues


def process(headers, rows, source_rows, cfg):
    norm = cfg["normalization"]; column_norms = norm.get("columns", {})
    rules = cfg["validation"].get("columns", {}); dedupe = cfg["dedupe"]
    referenced = set(column_norms) | set(rules) | set(dedupe.get("keys", []))
    missing = sorted(referenced - set(headers))
    if missing: raise CleanupError(f"Config references unknown column(s): {', '.join(missing)}")
    keys = list(dedupe.get("keys", [])) or list(headers)
    seen, cleaned, exceptions = {}, [], []
    changes, issues_count = Counter(), Counter()
    duplicates = validation_issues = 0
    for source_row, raw in zip(source_rows, rows):
        row, row_changes = {}, []
        for column in headers:
            row[column], cell_changes = normalize(raw.get(column, ""), norm, column_norms.get(column, {}))
            for change in cell_changes:
                changes[f"{column}:{change}"] += 1; row_changes.append(f"{column}:{change}")
        issues = []
        for column, column_rules in rules.items(): issues += validate(column, row.get(column, ""), column_rules)
        duplicate_of = None
        if dedupe.get("enabled", False):
            unsafe_keys = []
            for key_column in keys:
                key_value = row[key_column]
                key_rules = rules.get(key_column, {})
                if not key_value:
                    unsafe_keys.append((key_column, "blank"))
                elif validate(key_column, key_value, key_rules):
                    unsafe_keys.append((key_column, "invalid"))
            if unsafe_keys:
                for key_column, reason in unsafe_keys:
                    issues.append(f"dedupe_skipped_{reason}_key:{key_column}")
            else:
                key = tuple(row[k] if dedupe.get("case_sensitive", False) else row[k].casefold() for k in keys)
                if key in seen:
                    duplicate_of = seen[key]; issues.append(f"duplicate_of_source_row:{duplicate_of}"); duplicates += 1
                else: seen[key] = source_row
        validation_issues += sum(
            not i.startswith(("duplicate_of_source_row:", "dedupe_skipped_")) for i in issues
        )
        for issue in issues:
            if issue.startswith("duplicate_of_source_row:"):
                issue_key = "duplicate_of_source_row"
            elif issue.startswith("dedupe_skipped_"):
                issue_key = issue.split(":", 1)[0]
            else:
                issue_key = issue
            issues_count[issue_key] += 1
        if issues:
            exception = {"_source_row": str(source_row), "_issues": ";".join(issues), "_changes": ";".join(row_changes), **row}
            exceptions.append(exception)
        if duplicate_of is None: cleaned.append(row)
    metrics = {
        "source_rows": len(rows), "cleaned_rows": len(cleaned), "duplicate_rows_removed": duplicates,
        "exception_rows": len(exceptions), "validation_issue_count": validation_issues,
        "normalization_change_count": sum(changes.values()),
    }
    return cleaned, exceptions, metrics, dict(sorted(changes.items())), dict(sorted(issues_count.items()))


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)


def write_xlsx(path, headers, rows):
    if Workbook is None: raise CleanupError("XLSX support requires openpyxl")
    wb = Workbook(); ws = wb.active; ws.title = "cleaned"; ws.append(headers)
    for row in rows: ws.append([row.get(h, "") for h in headers])
    wb.save(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def run(input_path, config_path=None, output_dir=Path("cleanup-output"), overwrite=False):
    started = time.perf_counter()
    if not input_path.is_file(): raise CleanupError(f"Input file not found: {input_path}")
    cfg = config_from(config_path)
    headers, rows, source_rows, fmt, sheet = read_input(input_path, cfg)
    cleaned, exceptions, metrics, changes, issue_counts = process(headers, rows, source_rows, cfg)
    output_dir.mkdir(parents=True, exist_ok=True); stem = input_path.stem
    outputs = {
        "cleaned": output_dir / f"{stem}.cleaned.{fmt}", "exceptions": output_dir / f"{stem}.exceptions.csv",
        "report_json": output_dir / f"{stem}.report.json", "report_md": output_dir / f"{stem}.report.md",
    }
    existing = [p.name for p in outputs.values() if p.exists()]
    if existing and not overwrite: raise CleanupError(f"Refusing to overwrite: {', '.join(existing)}; use --overwrite")
    write_csv(outputs["cleaned"], headers, cleaned) if fmt == "csv" else write_xlsx(outputs["cleaned"], headers, cleaned)
    write_csv(outputs["exceptions"], ["_source_row", "_issues", "_changes"] + headers, exceptions)
    metrics["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    report = {
        "worker": "data-cleanup", "version": 1,
        "source": {"name": input_path.name, "sha256": sha256(input_path), "format": fmt, "sheet": sheet},
        "outputs": {k: v.name for k, v in outputs.items()}, "metrics": metrics,
        "normalization_changes": changes, "issue_counts": issue_counts, "config": cfg,
    }
    outputs["report_json"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = ["# Data Cleanup Run Report", "", f"- Source: `{input_path.name}`", f"- Source rows: **{metrics['source_rows']}**",
          f"- Cleaned rows: **{metrics['cleaned_rows']}**", f"- Exact duplicates removed: **{metrics['duplicate_rows_removed']}**",
          f"- Rows requiring review: **{metrics['exception_rows']}**", f"- Validation issues: **{metrics['validation_issue_count']}**",
          f"- Normalization changes: **{metrics['normalization_change_count']}**", "", "Source was read-only; no fuzzy matching or AI judgment was used."]
    outputs["report_md"].write_text("\n".join(md) + "\n", encoding="utf-8")
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deterministic CSV/XLSX cleanup with auditable outputs")
    parser.add_argument("input", type=Path); parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("cleanup-output")); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try: outputs = run(args.input, args.config, args.output_dir, args.overwrite)
    except CleanupError as exc: print(f"error: {exc}", file=sys.stderr); return 2
    for label, path in outputs.items(): print(f"{label}: {path}")
    return 0


if __name__ == "__main__": raise SystemExit(main())

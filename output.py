"""Output writers for CSV files, JSON files, and stdout."""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def write_csv(rows, output_dir, source_id):
    """Write rows to {output_dir}/{source_id}.csv. Returns filepath or None."""
    if not rows:
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"{source_id}.csv"

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    return filepath


def _utc_now_iso():
    """Current UTC time as ISO-8601 with a trailing Z (no offset suffix)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def write_json(rows, output_dir, source_id, parameters=None):
    """Write rows to {output_dir}/{source_id}.json wrapped in a metadata
    envelope (source, fetched_at, parameters, record_count, data).
    Returns filepath or None.
    """
    if not rows:
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"{source_id}.json"

    envelope = {
        "source": source_id,
        "fetched_at": _utc_now_iso(),
        "parameters": {k: v for k, v in (parameters or {}).items() if v is not None},
        "record_count": len(rows),
        "data": rows,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)

    return filepath


def write_stdout_json(rows):
    """Print JSON array to stdout for AI agent piping."""
    json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def emit_output(rows, source_id, output_dir, output_csv=False, output_json=False,
                stdout_json=False, output_both=False, parameters=None):
    """
    Write output based on flags. Returns dict with paths written and record count.

    --output-both writes both CSV and JSON files.
    Flags are combinable (e.g. --output-both --stdout-json).
    parameters is the run's CLI params dict, embedded in the JSON envelope.
    """
    if output_both:
        output_csv = True
        output_json = True

    result = {"csv": None, "json": None, "count": len(rows)}

    if output_csv:
        result["csv"] = write_csv(rows, output_dir, source_id)
    if output_json:
        result["json"] = write_json(rows, output_dir, source_id, parameters=parameters)
    if stdout_json:
        write_stdout_json(rows)

    return result

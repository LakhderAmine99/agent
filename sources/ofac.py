"""OFAC SDN List fetcher via Socrata JSON API or CSV bulk download."""

import csv
import io
import re
import time

from sources.base import get, log, parse_filter

SOCRATA_URL = "https://data.treasury.gov/resource/g7xk-mnex.json"
CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"

# Filter keys the CSV-bulk path can actually match. Country is intentionally
# excluded: the main sdn.csv carries no usable country column.
VALID_FILTERS = ["program", "sdn_type"]


def _build_where_clause(filters):
    """Build Socrata $where clause from filter dict."""
    if not filters:
        return None
    parts = []
    for key, val in filters.items():
        parts.append(f"{key}='{val}'")
    return " AND ".join(parts)


def _normalize_socrata_record(rec):
    return {
        "uid": rec.get("ent_num") or rec.get("uid"),
        "name": rec.get("sdn_name") or rec.get("name", ""),
        "sdn_type": rec.get("sdn_type", ""),
        "programs": rec.get("program", ""),
        "aliases": rec.get("alt_names", ""),
        "country": rec.get("country", ""),
        "date_of_birth": rec.get("date_of_birth", ""),
        "nationality": rec.get("nationality", ""),
        "id_type": rec.get("id_type", ""),
        "id_number": rec.get("id_number", ""),
        "remarks": rec.get("remarks", ""),
        "date_added": rec.get("date_added", ""),
    }


def _fetch_socrata(filters):
    where = _build_where_clause(filters)
    all_rows = []
    offset = 0
    limit = 10000

    while True:
        params = {"$limit": limit, "$offset": offset}
        if where:
            params["$where"] = where

        try:
            r = get(SOCRATA_URL, params=params, timeout=60)
            batch = r.json()
            if not batch:
                break

            for rec in batch:
                all_rows.append(_normalize_socrata_record(rec))

            log(f"  fetched {len(all_rows)} SDN entries so far")
            if len(batch) < limit:
                break
            offset += limit
            time.sleep(1)

        except Exception as e:
            log(f"  ofac socrata: {e}")
            break

    return all_rows


def _fetch_csv_bulk(filters):
    """Fallback: download full CSV and filter locally."""
    try:
        r = get(CSV_URL, timeout=120)
        reader = csv.reader(io.StringIO(r.text))
        all_rows = []

        for row in reader:
            if len(row) < 4:
                continue
            # OFAC uses "-0-" (sometimes with trailing space) as its null
            # sentinel; strip whitespace and blank those out.
            cleaned = ["" if cell.strip() == "-0-" else cell.strip() for cell in row]
            record = {
                "uid": cleaned[0],
                "name": cleaned[1],
                "sdn_type": cleaned[2],
                "programs": _normalize_programs(cleaned[3]),
                "aliases": "",
                "country": "",
                "date_of_birth": "",
                "nationality": "",
                "id_type": "",
                "id_number": "",
                "remarks": cleaned[11] if len(cleaned) > 11 else "",
                "date_added": "",
            }
            if _matches_filter(record, filters):
                all_rows.append(record)

        log(f"  CSV bulk: {len(all_rows)} entries after filter")
        return all_rows

    except Exception as e:
        log(f"  ofac csv: {e}")
        return []


def _normalize_programs(value):
    """Strip OFAC bracket formatting into a pipe-separated program list.

    '[IRAN] [SDGT] [IRGC]' -> 'IRAN | SDGT | IRGC'
    """
    stripped = re.sub(r"\[|\]", "", value)
    return " | ".join(p.strip() for p in stripped.split() if p.strip())


def _matches_filter(record, filters):
    if not filters:
        return True
    field_map = {"program": "programs"}
    for key, val in filters.items():
        field = field_map.get(key, key)
        field_val = str(record.get(field, "")).upper()
        if val.upper() not in field_val:
            return False
    return True


def fetch(recipe, params):
    filters = parse_filter(params.get("filter"))

    unknown = [k for k in filters if k not in VALID_FILTERS]
    if unknown:
        log(
            f"  Unknown filter '{unknown[0]}'. "
            f"Valid: {', '.join(VALID_FILTERS)}"
        )
        return []

    if filters:
        rows = _fetch_socrata(filters)
        if not rows:
            log("  Socrata returned no results, trying CSV bulk download...")
            rows = _fetch_csv_bulk(filters)
    else:
        rows = _fetch_csv_bulk({})

    return rows

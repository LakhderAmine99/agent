# ofac Handoff to Production

## 1. Working API call (live-verified)

### Primary path (no filter — full list)

```
GET https://www.treasury.gov/ofac/downloads/sdn.csv
```

| Parameter | Explanation |
|---|---|
| (none) | Single bulk CSV download; no query params |

- **Authentication:** none
- **Rate limits in practice:** No rate limit observed on CSV download. Full file (~5 MB) downloads in ~15–30s. No 429 encountered during live test.
- **Pagination strategy:** Not applicable — single file download. Parse entire CSV in memory.
- **Maximum reliable batch size:** Entire file (~19,000+ rows as of 2026-06-24). No chunking needed.

### Filtered path (with `--filter`)

Fetcher attempts Socrata first, then falls back to CSV bulk + local filter:

```
GET https://data.treasury.gov/resource/g7xk-mnex.json?$where=program='IRAN'&$limit=10000&$offset=0
```

| Parameter | Explanation |
|---|---|
| `$where` | Socrata SQL-like filter, e.g. `program='IRAN'`, `sdn_type='Individual'` |
| `$limit` | Page size (fetcher uses 10,000) |
| `$offset` | Pagination offset (increment by `$limit`) |

**Live finding:** Socrata endpoint currently returns HTTP 200 with `text/html` (not JSON). Fetcher catches JSON parse error and falls back to CSV bulk download + local substring filter. **Production should use CSV bulk or `sdn.xml` directly; do not rely on Socrata.**

- **Authentication:** none
- **Rate limits in practice:** Socrata unusable. CSV fallback: one download per filter query (~30s).
- **Pagination strategy (Socrata, if restored):** `$offset` += `$limit` until batch < limit.
- **Maximum reliable batch size:** CSV: full file. Socrata (historical): 10,000 per page.

### CLI verification command

```bash
python agent.py --source ofac --filter "program=IRAN" --stdout-json
```

---

## 2. Response shape (with real sample)

### Raw CSV (first 5 rows — no header row)

From `fixtures_ofac/success_csv_first5rows.json`:

```json
[
  ["36", "AEROCARIBBEAN AIRLINES", "-0- ", "CUBA", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- "],
  ["173", "ANGLO-CARIBBEAN CO., LTD.", "-0- ", "CUBA", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- "],
  ["306", "BANCO NACIONAL DE CUBA", "-0- ", "CUBA", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "a.k.a. 'BNC'."],
  ["424", "BOUTIQUE LA MAISON", "-0- ", "CUBA", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- "],
  ["475", "CASA DE CUBA", "-0- ", "CUBA", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- "]
]
```

### Normalized fetcher output (5 rows, `program=IRAN` filter)

```json
[
  {
    "uid": "4632",
    "name": "BANK MARKAZI JOMHOURI ISLAMI IRAN",
    "sdn_type": "",
    "programs": "IRAN | SDGT | IRGC | IFSR",
    "aliases": "",
    "country": "",
    "date_of_birth": "",
    "nationality": "",
    "id_type": "",
    "id_number": "",
    "remarks": "Additional Sanctions Information - Subject to Secondary Sanctions; ...",
    "date_added": ""
  },
  {
    "uid": "4633",
    "name": "BANK MASKAN",
    "sdn_type": "",
    "programs": "IRAN | IRAN-EO13902",
    "aliases": "",
    "country": "",
    "date_of_birth": "",
    "nationality": "",
    "id_type": "",
    "id_number": "",
    "remarks": "Website www.bankmaskan.ir; Additional Sanctions Information - Subject to Secondary Sanctions; all offices worldwide.",
    "date_added": ""
  },
  {
    "uid": "4635",
    "name": "BANK REFAH KARGARAN",
    "sdn_type": "",
    "programs": "IRAN | IRAN-EO13902",
    "aliases": "",
    "country": "",
    "date_of_birth": "",
    "nationality": "",
    "id_type": "",
    "id_number": "",
    "remarks": "Website www.bankrefah.ir; Additional Sanctions Information - Subject to Secondary Sanctions; all offices worldwide.",
    "date_added": ""
  },
  {
    "uid": "4640",
    "name": "BANK SEPAH",
    "sdn_type": "",
    "programs": "IRAN | SDGT | IRGC | IFSR",
    "aliases": "",
    "country": "",
    "date_of_birth": "",
    "nationality": "",
    "id_type": "",
    "id_number": "",
    "remarks": "Additional Sanctions Information - Subject to Secondary Sanctions; ...",
    "date_added": ""
  },
  {
    "uid": "4641",
    "name": "BANK SEPAH INTERNATIONAL",
    "sdn_type": "",
    "programs": "IRAN | SDGT | IRGC | IFSR",
    "aliases": "",
    "country": "",
    "date_of_birth": "",
    "nationality": "",
    "id_type": "",
    "id_number": "",
    "remarks": "Additional Sanctions Information - Subject to Secondary Sanctions; ...",
    "date_added": ""
  }
]
```

### Field mapping to canonical columns

| Canonical column | Source field | Notes |
|---|---|---|
| `event_date` | *(blank)* | `date_added` exists in schema but is empty via CSV path. Use snapshot/fetch date in production. |
| `value` | *(blank)* | Entity reference data, not a numeric time series. |
| `unit` | *(blank)* | N/A |
| `source_notes` | `programs` + `remarks` | Pipe-separated programs; free-text remarks |
| `record_key` | `uid` | OFAC entity number; unique per SDN entry |

---

## 3. Vintage / point-in-time honest assessment

- **Does this API expose vintage?** **no**
- **Details:** The SDN list is a current-state snapshot. No vintage or as-of-revision parameter exists. Daily delta file (`sdn_deltas.xml`) tracks additions/removals but is not vintage in the economic-data sense.
- **DEV2 setting:** `vintage_supported=false`

---

## 4. Update strategy

| Question | Answer |
|---|---|
| Natural watermark field | Snapshot date (`fetched_at`) or Treasury publish date (not in CSV). For incremental: parse `sdn_deltas.xml` daily. |
| New vs revised data | Compare daily snapshots by `uid`. New UIDs = additions; missing UIDs = removals. Field changes require diffing `name`, `programs`, `remarks`. |
| Re-fetch overlap window | Re-download full CSV daily. No overlap needed for full refresh. For deltas: use `sdn_deltas.xml` instead of full re-download. |

---

## 5. Known failure modes we hit

| Failure | Cause | Behavior |
|---|---|---|
| Socrata returns HTML (HTTP 200) | Endpoint appears deprecated/broken | JSON parse fails; fetcher falls back to CSV bulk |
| `Unknown filter 'country'` | `country=` not supported | CLI exits 1 immediately |
| `No data retrieved` (exit 1) | Filter matches zero rows after CSV scan | e.g. `program=ZZZZNONEXISTENT` |
| HTTP 503 | Treasury server busy | `sources/base.py` retries after 60s (up to 3 attempts) |
| HTTP 429 | Rate limited | Retries after `Retry-After` header (not hit in live test) |
| `-0-` sentinel in CSV | OFAC null marker | Stripped to empty string by fetcher |
| Slow filtered queries | Full CSV download on every filtered request | ~30s per filter query |

---

## 6. Output column mapping

| DEV1 key | DEV2 canonical column | Notes |
|---|---|---|
| `uid` | `record_key` | Primary unique identifier |
| `name` | `source_notes` (partial) | Entity name; include in notes |
| `sdn_type` | `source_notes` (partial) | Individual/Entity/Vessel/Aircraft; blank in CSV path |
| `programs` | `source_notes` (partial) | Pipe-separated sanctions programs |
| `aliases` | `source_notes` (partial) | Blank via CSV; populated via Socrata/XML |
| `country` | *(blank)* | Not in bulk CSV |
| `date_of_birth` | *(blank)* | Not in bulk CSV |
| `nationality` | *(blank)* | Not in bulk CSV |
| `id_type` | *(blank)* | Not in bulk CSV |
| `id_number` | *(blank)* | Not in bulk CSV |
| `remarks` | `source_notes` (partial) | Free-text remarks |
| `date_added` | `event_date` | Blank via CSV; available in XML/deltas |

**Blank canonical columns:** `event_date`, `value`, `unit` — entity list, not time-series data.

**Transformations needed:**
- Strip `-0-` null sentinel → empty string
- Normalize programs: `[IRAN] [SDGT]` → `IRAN | SDGT`
- `sdn_type` filter: case-insensitive substring match on `programs` field

---

## 7. Test fixtures

| File | Description |
|---|---|
| `fixtures_ofac/success_csv_first5rows.json` | Raw CSV first 5 rows (success) |
| `fixtures_ofac/error_socrata_returns_html.json` | Socrata returns HTML instead of JSON (error) |
| `fixtures_ofac/empty_filter_no_match.json` | Socrata empty result (empty; also reproducible via CLI with bogus program) |
| `fixtures_ofac/error_bad_socrata_where.json` | Invalid Socrata `$where` clause response |
| `fixtures_ofac/empty_filter_no_match.json` | No matches for impossible program filter |

CLI test log: `cli_test_log_ofac.txt` — live run, exit 0, 2375 records for `program=IRAN`.

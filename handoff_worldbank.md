# worldbank Handoff to Production

## 1. Working API call (live-verified)

### URL pattern

```
GET https://api.worldbank.org/v2/country/{countries}/indicator/{indicator_code}?format=json&date={start}:{end}&per_page={per_page}&page={page}
```

| Parameter | Explanation |
|---|---|
| `{countries}` | ISO-2 codes semicolon-separated (`US;GB;DE`) or `all` |
| `{indicator_code}` | World Bank indicator code, e.g. `NY.GDP.MKTP.KD.ZG` |
| `format` | Must be `json` |
| `date` | Year range `YYYY:YYYY`, e.g. `2020:2024` |
| `per_page` | Records per page; max 20,000 |
| `page` | Page number (1-indexed) |

### Example (live-verified)

```
GET https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.KD.ZG?format=json&date=2020:2024&per_page=20000&page=1
```

- **Authentication:** none
- **Rate limits in practice:** No 429 hit during live test. Fetcher sleeps 1s between pages and between indicators as precaution.
- **Pagination strategy:** Read `response[0].pages`; increment `page` until `page >= pages`. Use `per_page=20000` to minimize pages.
- **Maximum reliable batch size:** `per_page=20000` handles most single-indicator/country combos in one page.

### CLI verification command

```bash
python agent.py --source worldbank --indicators "NY.GDP.MKTP.KD.ZG" --countries "US,GB" --start 2020 --stdout-json
```

Live result: **10 records**, exit 0.

---

## 2. Response shape (with real sample)

Response is a **2-element JSON array**: `[metadata, data]`.

### Metadata (`response[0]`)

```json
{
  "page": 1,
  "pages": 1,
  "per_page": 20000,
  "total": 5,
  "sourceid": "2",
  "lastupdated": "2026-04-08"
}
```

### Data — 5 rows (`response[1]`)

From `fixtures_worldbank/success_us_gdp_growth_5rows.json`:

```json
[
  {
    "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
    "country": {"id": "US", "value": "United States"},
    "countryiso3code": "USA",
    "date": "2024",
    "value": 2.79300127716779,
    "unit": "",
    "obs_status": "",
    "decimal": 1
  },
  {
    "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
    "country": {"id": "US", "value": "United States"},
    "countryiso3code": "USA",
    "date": "2023",
    "value": 2.88755600749487,
    "unit": "",
    "obs_status": "",
    "decimal": 1
  },
  {
    "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
    "country": {"id": "US", "value": "United States"},
    "countryiso3code": "USA",
    "date": "2022",
    "value": 2.51237531986017,
    "unit": "",
    "obs_status": "",
    "decimal": 1
  },
  {
    "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
    "country": {"id": "US", "value": "United States"},
    "countryiso3code": "USA",
    "date": "2021",
    "value": 6.05505293244555,
    "unit": "",
    "obs_status": "",
    "decimal": 1
  },
  {
    "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
    "country": {"id": "US", "value": "United States"},
    "countryiso3code": "USA",
    "date": "2020",
    "value": -2.16302914036166,
    "unit": "",
    "obs_status": "",
    "decimal": 1
  }
]
```

### Field mapping to canonical columns

| Canonical column | API / DEV1 field | Notes |
|---|---|---|
| `event_date` | `date` → `year` | Annual granularity; store as `YYYY` or `YYYY-01-01` |
| `value` | `value` | Float; null values dropped by fetcher |
| `unit` | `unit` | Usually empty string; meaning in `indicator.value` label |
| `source_notes` | `indicator_name` | e.g. "GDP Growth Rate %" |
| `record_key` | `{country_code}:{indicator_code}:{year}` | e.g. `US:NY.GDP.MKTP.KD.ZG:2024` |

---

## 3. Vintage / point-in-time honest assessment

- **Does this API expose vintage?** **partial**
- **Details:** World Bank revises historical indicator values over time, but the API returns only the **latest revision**. There is no `vintage` or `as_of` parameter. `lastupdated` in metadata is the dataset refresh date, not per-observation vintage.
- **DEV2 setting:** `vintage_supported=false` (or `partial` if your schema distinguishes dataset-level revision tracking)

---

## 4. Update strategy

| Question | Answer |
|---|---|
| Natural watermark field | `response[0].lastupdated` (dataset level) or max `year` in fetched data |
| New vs revised data | Re-fetch full date range periodically; compare `value` for same `record_key`. Revisions appear as changed values for existing country/indicator/year. |
| Re-fetch overlap window | Re-fetch last 2–3 years on each run to capture revisions to recent data. |

---

## 5. Known failure modes we hit

| Failure | Cause | Behavior |
|---|---|---|
| HTTP 400 / API message id 120 | Invalid indicator code | Returns `[{message: [{id: "120", key: "Invalid value"}]}]` with HTTP 200 |
| Null `value` in response | No data for that year/country | Fetcher silently drops; can result in 0 records |
| Invalid country code (`XX`) | Country not found | Returns rows with null values; fetcher outputs 0 records, CLI exits 1 |
| HTTP 429 | Rate limited | `sources/base.py` waits `Retry-After` and retries (not hit in live test) |
| HTTP 503 | Server busy | Retries after 60s |

---

## 6. Output column mapping

| DEV1 key | DEV2 canonical column | Notes |
|---|---|---|
| `country_code` | `record_key` (partial) | ISO-2 country code |
| `country_name` | `source_notes` (partial) | Human-readable country name |
| `indicator_code` | `record_key` (partial) | World Bank indicator ID |
| `indicator_name` | `source_notes` | Friendly label from fetcher's `INDICATOR_NAMES` dict |
| `year` | `event_date` | String year, e.g. `"2024"` |
| `value` | `value` | Float |

**Blank canonical columns:** `unit` — API `unit` field is usually empty; unit semantics are embedded in `indicator_name` (e.g. "%").

**Transformations needed:**
- `date` (API) → `year` (DEV1): direct string copy
- Filter `value is not None`
- `countries` CLI param: comma-separated → semicolon-separated in URL
- `end=present` → current calendar year

---

## 7. Test fixtures

| File | Description |
|---|---|
| `fixtures_worldbank/success_us_gdp_growth.json` | Full API response with metadata + data |
| `fixtures_worldbank/success_us_gdp_growth_5rows.json` | 5 data rows only (success) |
| `fixtures_worldbank/empty_invalid_country.json` | Country `XX` — rows with null values (empty after filtering) |
| `fixtures_worldbank/error_invalid_indicator.json` | Invalid indicator code `INVALID.CODE.XYZ` |

CLI test log: `cli_test_log_worldbank.txt` — live run, exit 0, 10 records.

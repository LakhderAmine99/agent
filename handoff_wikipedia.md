# wikipedia Handoff to Production

## 1. Working API call (live-verified)

### URL pattern

```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/{access}/{agent}/{article}/daily/{start}/{end}
```

| Parameter | Explanation |
|---|---|
| `{project}` | Wiki project, e.g. `en.wikipedia` |
| `{access}` | `all-access`, `desktop`, `mobile-app`, `mobile-web` |
| `{agent}` | `all-agents`, `user`, `spider`, `automated` |
| `{article}` | Article title with underscores for spaces, URL-encoded |
| `{start}` | Start date `YYYYMMDD` (minimum `20150701`) |
| `{end}` | End date `YYYYMMDD` |

### Example (live-verified)

```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/Inflation/daily/20230101/20230105
```

- **Authentication:** none
- **Rate limits in practice:** No 429 hit during live test. Fetcher sleeps 0.5s between articles. API docs suggest ~5 req/s; `sources/base.py` handles 429 with `Retry-After`.
- **Pagination strategy:** Not needed — single request returns full date range per article. For many articles: one request per article.
- **Maximum reliable batch size:** One article per request; date range limited only by API availability (data from 2015-07-01).

### CLI verification command

```bash
python agent.py --source wikipedia --articles "Inflation" --start 2023-01-01 --end 2023-01-31 --stdout-json
```

Live result: **31 records**, exit 0.

---

## 2. Response shape (with real sample)

### 5-row sample

From `fixtures_wikipedia/success_inflation_5rows.json`:

```json
{
  "items": [
    {
      "project": "en.wikipedia",
      "article": "Inflation",
      "granularity": "daily",
      "timestamp": "2023010100",
      "access": "all-access",
      "agent": "all-agents",
      "views": 2030
    },
    {
      "project": "en.wikipedia",
      "article": "Inflation",
      "granularity": "daily",
      "timestamp": "2023010200",
      "access": "all-access",
      "agent": "all-agents",
      "views": 2826
    },
    {
      "project": "en.wikipedia",
      "article": "Inflation",
      "granularity": "daily",
      "timestamp": "2023010300",
      "access": "all-access",
      "agent": "all-agents",
      "views": 3064
    },
    {
      "project": "en.wikipedia",
      "article": "Inflation",
      "granularity": "daily",
      "timestamp": "2023010400",
      "access": "all-access",
      "agent": "all-agents",
      "views": 3072
    },
    {
      "project": "en.wikipedia",
      "article": "Inflation",
      "granularity": "daily",
      "timestamp": "2023010500",
      "access": "all-access",
      "agent": "all-agents",
      "views": 3386
    }
  ]
}
```

### Field mapping to canonical columns

| Canonical column | API / DEV1 field | Notes |
|---|---|---|
| `event_date` | `date` | Parsed from `timestamp` (`YYYYMMDD` → `YYYY-MM-DD`) |
| `value` | `views` | Integer daily pageview count |
| `unit` | `pageviews` | Implicit; not in API response |
| `source_notes` | `article` | Article title |
| `record_key` | `{article}:{date}:{project}:{access}:{agent}` | e.g. `Inflation:2023-01-01:en.wikipedia:all-access:all-agents` |

---

## 3. Vintage / point-in-time honest assessment

- **Does this API expose vintage?** **no**
- **Details:** Pageview counts are final once published. No revision/vintage parameter. Historical data before 2015-07-01 is unavailable.
- **DEV2 setting:** `vintage_supported=false`

---

## 4. Update strategy

| Question | Answer |
|---|---|
| Natural watermark field | Max `date` in fetched data per article |
| New vs revised data | New days appended daily. Counts are not revised after publication. |
| Re-fetch overlap window | Re-fetch last 3 days on each run to catch late-arriving data (~1 hour latency after midnight UTC). |

---

## 5. Known failure modes we hit

| Failure | Cause | Behavior |
|---|---|---|
| HTTP 404 | Article not found OR dates before 2015-07-01 | JSON error body with `detail` message; fetcher logs error, continues |
| HTTP 429 | Rate limited | `sources/base.py` waits `Retry-After` and retries |
| HTTP 500 | Server error | Retry after 120s (per catalog; base.py retries 503) |
| Empty `items` array | Valid request but no data for date range | Returns `{"items": []}`; CLI exits 1 if all articles empty |
| Article title encoding | Spaces vs underscores | Use underscores; URL-encode special characters |

---

## 6. Output column mapping

| DEV1 key | DEV2 canonical column | Notes |
|---|---|---|
| `article` | `source_notes` / `record_key` (partial) | Wikipedia article title |
| `date` | `event_date` | `YYYY-MM-DD` converted from `timestamp` |
| `views` | `value` | Integer |
| `project` | `record_key` (partial) | e.g. `en.wikipedia` |
| `access` | `record_key` (partial) | e.g. `all-access` |
| `agent` | `record_key` (partial) | e.g. `all-agents` |

**Blank canonical columns:** `unit` — not in API; set to `pageviews` in production if required.

**Transformations needed:**
- `YYYY-MM-DD` → `YYYYMMDD` for URL path (`start`/`end` params)
- `timestamp[:4]+'-'+timestamp[4:6]+'-'+timestamp[6:8]` → `date`
- `end=today` → current date as `YYYYMMDD`
- Minimum start date: `2015-07-01`

---

## 7. Test fixtures

| File | Description |
|---|---|
| `fixtures_wikipedia/success_inflation_5days.json` | Full API response for 5-day range |
| `fixtures_wikipedia/success_inflation_5rows.json` | 5 `items` rows (success) |
| `fixtures_wikipedia/empty_pre2015_date_range.json` | Dates before 2015-07-01 → HTTP 404 (empty) |
| `fixtures_wikipedia/error_article_not_found_404.json` | Nonexistent article → HTTP 404 |

CLI test log: `cli_test_log_wikipedia.txt` — live run, exit 0, 31 records.

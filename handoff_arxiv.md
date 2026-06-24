# arxiv Handoff to Production

## 1. Working API call (live-verified)

### URL pattern

```
GET http://export.arxiv.org/api/query?search_query={query}&start={offset}&max_results={batch}&sortBy=submittedDate&sortOrder=descending
```

| Parameter | Explanation |
|---|---|
| `search_query` | Boolean query with field prefixes: `cat:`, `abs:`, `ti:`, `au:`, `all:` |
| `start` | Pagination offset (0-indexed) |
| `max_results` | Results per page (max 2,000) |
| `sortBy` | `submittedDate`, `lastUpdatedDate`, or `relevance` |
| `sortOrder` | `ascending` or `descending` |

### Example (live-verified)

```
GET http://export.arxiv.org/api/query?search_query=cat:econ.GN+AND+abs:inflation&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending
```

Fetcher builds query from CLI: `cat:{category}+AND+abs:{keyword}`; defaults to `all:*` if neither set.

- **Authentication:** none
- **Rate limits in practice:** arXiv policy: max 1 request per 3 seconds. Fetcher sleeps 3s between pages. No 429 hit during live test.
- **Pagination strategy:** Increment `start` by number of entries returned; stop when `start >= max_results` or batch < requested size.
- **Maximum reliable batch size:** 2,000 per request (`max_results` API cap).

### CLI verification command

```bash
python agent.py --source arxiv --category "econ.GN" --keyword "inflation" --max-results 10 --stdout-json
```

Live result: **10 records**, exit 0.

---

## 2. Response shape (with real sample)

Response format is **Atom XML** (not JSON). Parsed via `feedparser`.

### 5-row parsed sample

From `fixtures_arxiv/success_econ_gn_inflation_5entries.json`:

```json
[
  {
    "id": "http://arxiv.org/abs/2606.22337v2",
    "title": "Theorist Toolbox: Tools for Agent Based LLM-assisted economic theory Research",
    "summary": "Empirical economists often start their projects with a toolbox...",
    "published": "2026-06-21T05:03:37Z",
    "updated": "2026-06-23T07:45:44Z",
    "authors": ["Moran Koren"],
    "tags": ["econ.TH", "cs.GT", "econ.GN"]
  },
  {
    "id": "http://arxiv.org/abs/2606.20041v1",
    "title": "AI Economist Agent: An Agentic Framework for Model-Grounded Economic Analysis with RAG, Knowledge Graphs, and Large Language Models",
    "summary": "We propose a model-grounded RAG-based AI economist...",
    "published": "2026-06-18T10:18:03Z",
    "updated": "2026-06-18T10:18:03Z",
    "authors": ["Masahiro Kato"],
    "tags": ["econ.GN", "cs.AI", "cs.LG", "q-fin.GN"]
  },
  {
    "id": "http://arxiv.org/abs/2606.09944v1",
    "title": "GAGI: A Gini-Adjusted GDP-per-Capita Index for Distribution-Aware Macroeconomic Welfare Monitoring",
    "summary": "GDP per capita is the default lens through which governibng bodies track...",
    "published": "2026-06-08T03:30:20Z",
    "updated": "2026-06-08T03:30:20Z",
    "authors": ["Sivasathivel Kandasamy"],
    "tags": ["econ.GN", "cs.AI"]
  },
  {
    "id": "http://arxiv.org/abs/2605.27265v2",
    "title": "Quantifying Social Inflation in Liability Insurance with Advanced Statistical Methods",
    "summary": "Social inflation, which is the rise in liability claim costs beyond general economic inflation...",
    "published": "2026-05-26T16:42:07Z",
    "updated": "2026-05-28T13:57:04Z",
    "authors": ["Tsz Chai Fung", "Lie Ma", "Liang Peng"],
    "tags": ["econ.GN", "stat.AP", "stat.ME"]
  },
  {
    "id": "http://arxiv.org/abs/2605.24356v1",
    "title": "Contested Temporalities in Critical Minerals and Resource Extraction for Electric Vehicles",
    "summary": "The global push for electric vehicles (EVs) has sharply increased demand for critical minerals...",
    "published": "2026-05-23T02:35:08Z",
    "updated": "2026-05-23T02:35:08Z",
    "authors": ["Joseph Nyangon"],
    "tags": ["eess.SY", "econ.GN", "stat.AP", "stat.OT"]
  }
]
```

### Field mapping to canonical columns

| Canonical column | DEV1 field | Notes |
|---|---|---|
| `event_date` | `submitted_date` | `published` truncated to `YYYY-MM-DD` |
| `value` | `1` (per paper) or `title_word_count` / `abstract_word_count` | Depends on use case; default 1 record per paper |
| `unit` | `count` or `words` | If using word counts |
| `source_notes` | `title` + truncated `abstract` | Abstract capped at 500 chars in fetcher |
| `record_key` | `arxiv_id` | e.g. `2606.22337v2` (includes version suffix) |

---

## 3. Vintage / point-in-time honest assessment

- **Does this API expose vintage?** **no**
- **Details:** `updated_date` reflects metadata/abstract revisions, not economic vintage. No as-of parameter.
- **DEV2 setting:** `vintage_supported=false`

---

## 4. Update strategy

| Question | Answer |
|---|---|
| Natural watermark field | `submitted_date` (for new papers) or `updated_date` (for metadata changes) |
| New vs revised data | New: `submitted_date >= last_watermark`. Revised: same `arxiv_id` base with higher version suffix or changed `updated_date`. |
| Re-fetch overlap window | Re-query last 7 days by `submittedDate` descending to catch late-indexed papers. |

---

## 5. Known failure modes we hit

| Failure | Cause | Behavior |
|---|---|---|
| Empty results | No papers match query | `feed.entries` empty; CLI exits 1 |
| HTTP 503 | Service unavailable | Retries after 60s via `sources/base.py` (arXiv uses feedparser directly, not `get()`) |
| Rate limiting | Too-frequent requests | Must sleep ≥3s between requests; not enforced by API response but by policy |
| Malformed query | Invalid search syntax | API may still return results (treats tokens as search terms); see `error_malformed_query.json` |
| `start` date filter | Client-side only | Fetcher filters `submitted < start_date` after fetch; wastes API calls |

---

## 6. Output column mapping

| DEV1 key | DEV2 canonical column | Notes |
|---|---|---|
| `arxiv_id` | `record_key` | Parsed from `entry.id` URL tail |
| `title` | `source_notes` (partial) | Newlines stripped |
| `abstract` | `source_notes` (partial) | Truncated to 500 chars |
| `submitted_date` | `event_date` | ISO date `YYYY-MM-DD` |
| `updated_date` | *(metadata)* | Not mapped to canonical; useful for revision tracking |
| `primary_category` | `source_notes` (partial) | e.g. `econ.GN` |
| `all_categories` | `source_notes` (partial) | Pipe-separated |
| `authors` | `source_notes` (partial) | Pipe-separated, max 5 |
| `title_word_count` | `value` (optional) | Integer word count |
| `abstract_word_count` | `value` (optional) | Integer word count |

**Blank canonical columns:** `unit` — unless explicitly set to `count` or `words` based on use case.

**Transformations needed:**
- `entry.id.split("/")[-1]` → `arxiv_id`
- `published[:10]` → `submitted_date`
- `updated[:10]` → `updated_date`
- Newline removal in title/abstract
- `+AND+` join for multi-part search queries

---

## 7. Test fixtures

| File | Description |
|---|---|
| `fixtures_arxiv/success_econ_gn_inflation_5entries.json` | 5 parsed paper entries (success) |
| `fixtures_arxiv/success_econ_gn_inflation_raw.xml.json` | Raw Atom XML response preview |
| `fixtures_arxiv/empty_impossible_keyword.json` | Zero results for nonsense keyword |
| `fixtures_arxiv/error_malformed_query.json` | Malformed query (API still returns HTTP 200 with unexpected matches) |

CLI test log: `cli_test_log_arxiv.txt` — live run, exit 0, 10 records.

# Fetch Agent + JSON Recipe Catalog

A generic, recipe-driven data fetch agent. Each data source is described by a
JSON "recipe" in `catalog/`. An AI agent (or a human) reads the catalog to
discover what data exists, then calls `agent.py` with the documented flags to
get clean **CSV** and/or **JSON** output. No API keys are required for any
source.

**Currently supported:** Wikipedia pageviews, World Bank indicators, arXiv
papers, OFAC sanctions list, IMF (see [IMF status](#imf-source-status)).

---

## 1. Setup

**Requirements:** Python **3.8 or newer** (tested on 3.14). No API keys, no
accounts, no secrets — every source is a public API.

```bash
# 1. Clone or unzip the project, then enter the directory that contains agent.py
cd agent

# 2. (Recommended) create and activate a virtual environment
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

# 3. Install the three dependencies (requests, feedparser, pycountry)
pip install -r requirements.txt

# 4. Verify the install — this should print usage with all flags and sources
python agent.py --help
```

If `--help` prints the usage block listing
`--source {wikipedia,imf,worldbank,arxiv,ofac}`, you are fully operational.

---

## 2. Project structure

```
agent/
├── agent.py            # CLI entry point: parse args → load recipe → fetch → write output
├── output.py           # CSV / JSON writers (+ the JSON metadata envelope)
├── requirements.txt    # requests, feedparser, pycountry
├── README.md           # this file
├── .gitignore          # ignores data/* and Python caches
├── catalog/            # one JSON "recipe" per source — the data the agent reads to know HOW to fetch
│   ├── index.json      # MASTER INDEX — read this first; lists all sources + the IMF→World Bank map
│   ├── wikipedia.json
│   ├── worldbank.json
│   ├── arxiv.json
│   ├── ofac.json
│   └── imf.json
├── sources/            # the Python fetchers — the code that knows HOW to call each API
│   ├── __init__.py     # lazy fetcher registry (one broken source can't crash the others)
│   ├── base.py         # shared HTTP GET with retry/backoff + small parse helpers
│   ├── wikipedia.py
│   ├── worldbank.py
│   ├── arxiv.py
│   ├── ofac.py
│   └── imf.py
└── data/               # OUTPUT directory (default). Files land here; gitignored except .gitkeep
```

- **`catalog/`** is documentation-as-data: each recipe describes a source's
  endpoints, parameters, rate limits, and output schema. Editing a recipe needs
  no code change.
- **`sources/`** is the matching code: each `<source>.py` exposes a
  `fetch(recipe, params)` function returning a list of dict rows.
- **`data/`** is where output is written. Override with `--output-dir`.

---

## 3. How it works (recipe-driven architecture)

The catalog (data) and the fetchers (code) are kept separate so new sources can
be added by dropping in a recipe + a small fetcher. The intended workflow:

1. **Discover** — read [`catalog/index.json`](catalog/index.json) to see every
   available source, its category, and example calls.
2. **Read the recipe** — open the specific source file, e.g.
   [`catalog/worldbank.json`](catalog/worldbank.json), for endpoints,
   parameters, and the output schema.
3. **Fetch** — run `agent.py` with the documented flags.
4. **Ingest** — use the CSV for pipelines, or the JSON (with metadata envelope)
   for analysis.

`agent.py` loads `catalog/<source>.json`, validates required params against the
recipe, dispatches to `sources/<source>.py`, and writes the result.

---

## 4. Command-line reference

### All parameters

| Flag | Applies to | Required | Default | Description |
|------|-----------|----------|---------|-------------|
| `--source` | all | **yes** | — | One of: `wikipedia`, `worldbank`, `arxiv`, `ofac`, `imf` |
| `--articles` | wikipedia | **yes** | — | Comma-separated article titles (underscores for spaces) |
| `--indicators` | worldbank, imf | **yes** | — | Comma-separated indicator codes |
| `--countries` | worldbank, imf | no | `all` | Comma-separated ISO-2 codes, or `all` |
| `--category` | arxiv | no | — | arXiv category, e.g. `cs.AI`, `econ.GN` |
| `--keyword` | arxiv | no | — | Keyword searched in the abstract |
| `--max-results` | arxiv | no | `100` | Max papers to fetch |
| `--filter` | ofac | no | — | `program=...` or `sdn_type=...` (see [OFAC](#ofac-filters)) |
| `--start` | all | no | varies | Start date/year (`YYYY-MM-DD` or `YYYY`) |
| `--end` | all | no | varies | End date/year |
| `--output-dir` | all | no | `./data` | Directory for output files |

### Output flags

| Flag | Description |
|------|-------------|
| `--output-csv` | Write `{output_dir}/{source}.csv` — **this is the default if no output flag is given** |
| `--output-json` | Write `{output_dir}/{source}.json` (metadata envelope, see below) |
| `--output-both` | Write both CSV and JSON files |
| `--stdout-json` | Print a **bare JSON array** to stdout (for piping into another tool) |

Flags are combinable (e.g. `--output-both --stdout-json`). Status/progress
messages go to **stderr**, so stdout stays clean when piping `--stdout-json`.

### JSON envelope (`--output-json` / `--output-both`)

File JSON is wrapped with run metadata:

```json
{
  "source": "wikipedia",
  "fetched_at": "2026-06-23T14:00:00.000000Z",
  "parameters": { "articles": "Inflation", "start": "2023-01-01" },
  "record_count": 365,
  "data": [ { "article": "Inflation", "date": "2023-01-01", "views": 2030, "...": "..." } ]
}
```

> Note: `--stdout-json` intentionally prints just the bare `data` array (no
> envelope), so it pipes cleanly into `jq` and similar tools.

---

## 5. Sources & working examples

Every command below is copy-paste ready. Progress lines shown are from stderr.

### Wikipedia — daily pageviews
Params: `--articles` (required), `--start` (default `2015-07-01`), `--end`
(default today).

```bash
python agent.py --source wikipedia \
  --articles "Inflation,Housing_market" \
  --start 2023-01-01 --end 2023-12-31 \
  --output-both
```
```
  Inflation: 365 records
  Housing_market: 365 records
Done: 730 records
  CSV:  data/wikipedia.csv
  JSON: data/wikipedia.json
```
CSV columns: `article, date, views, project, access, agent`.

### World Bank — macroeconomic indicators
Params: `--indicators` (required), `--countries` (default `all`), `--start`
(default `2000`), `--end` (default current year). Indicator codes get friendly
labels (e.g. `NY.GDP.MKTP.KD.ZG` → `GDP Growth Rate %`).

```bash
python agent.py --source worldbank \
  --indicators "NY.GDP.MKTP.KD.ZG,FP.CPI.TOTL.ZG" \
  --countries "US,GB,DE" \
  --start 2015 \
  --output-both
```
```
  GDP Growth Rate %: 30 records
  Inflation CPI %: 30 records
Done: 60 records
```
CSV columns: `country_code, country_name, indicator_code, indicator_name, year, value`.
Common codes: `NY.GDP.MKTP.KD.ZG` (GDP growth %), `FP.CPI.TOTL.ZG` (inflation %),
`SL.UEM.TOTL.ZS` (unemployment %), `GC.DOD.TOTL.GD.ZS` (govt debt % GDP),
`SP.POP.TOTL` (population). See [`catalog/worldbank.json`](catalog/worldbank.json)
for the full list.

### arXiv — research papers
Params: `--category`, `--keyword`, `--max-results` (default `100`), `--start`
(keep only papers submitted on/after this date). arXiv asks for ~3s between
requests; the fetcher sleeps automatically.

```bash
python agent.py --source arxiv \
  --category "econ.GN" \
  --keyword "inflation" \
  --max-results 20 \
  --output-both
```
```
  fetched 20 papers so far
Done: 20 records
```
CSV columns: `arxiv_id, title, abstract, submitted_date, updated_date,
primary_category, all_categories, title_word_count, abstract_word_count, authors`.

### OFAC — sanctions (SDN) list
Param: `--filter` (optional). With no filter you get the full list (~19,000 rows).

```bash
python agent.py --source ofac \
  --filter "program=IRAN" \
  --output-both
```
```
  CSV bulk: 2375 entries after filter
Done: 2375 records
```
CSV columns: `uid, name, sdn_type, programs, aliases, country, date_of_birth,
nationality, id_type, id_number, remarks, date_added`. The `-0-` null marker is
stripped to empty, and `programs` is normalized to pipe-separated
(`IRAN | SDGT | IRGC`).

> Data note: the live source is the bulk `sdn.csv`, which populates `uid`,
> `name`, `sdn_type`, `programs`, and `remarks`. The other columns exist in the
> schema but are blank in this file.

<a name="ofac-filters"></a>**Valid `--filter` keys (only these two):**

| Filter | Example values |
|--------|----------------|
| `program=` | `RUSSIA`, `IRAN`, `DPRK`, `SDGT`, `CUBA`, `SYRIA`, `VENEZUELA`, `CYBER`, `GLOMAG` |
| `sdn_type=` | `individual`, `entity`, `vessel`, `aircraft` |

`country=` is **not supported** (the bulk CSV has no usable country column) — it
returns a clear error and exit code 1.

### IMF — macroeconomic data
Params: `--indicators` (required), `--countries`, `--start`, `--end`.

<a name="imf-source-status"></a>**IMF source status — read this:** the IMF
DataMapper API currently returns HTTP **403** for automated requests (a
server-side block, outside our control). The `imf` source therefore returns a
single *fallback note row* rather than data, and exits 0:

```bash
python agent.py --source imf --indicators "NGDP_RPCH" --countries "US" --start 2020 --output-both
```
```
IMF API currently blocking automated requests. Use --source worldbank for overlapping indicators.
Done: 1 records
```

**Use World Bank instead.** `catalog/index.json` contains an
`imf_to_worldbank_mapping`. For example, IMF `NGDP_RPCH` → World Bank
`NY.GDP.MKTP.KD.ZG`:

```bash
python agent.py --source worldbank \
  --indicators "NY.GDP.MKTP.KD.ZG" \
  --countries "US" --start 2020 \
  --output-both
```

---

## 6. Error handling & exit codes

| Situation | Behavior |
|-----------|----------|
| **Rate limited (HTTP 429)** | Waits the `Retry-After` interval, then retries (up to 3 attempts) |
| **Server busy (HTTP 503)** | Waits 60s and retries (up to 3 attempts) |
| **Invalid `--source`** | argparse prints `invalid choice: ...`, exits **2** |
| **Missing required param** | Prints e.g. `Error: --articles is required for wikipedia source`, exits **1** |
| **Unknown OFAC filter** | Prints `Unknown filter 'country'. Valid: program, sdn_type`, exits **1** |
| **No data returned** | Prints `No data retrieved for <source>`, exits **1** |
| **Success** | Prints record count + file paths, exits **0** |

**Exit codes:** `0` = success, `1` = handled error (bad params / no data),
`2` = command-line usage error.

---

## 7. Adding a new source (Phase 2)

Three steps — no changes to `agent.py` needed:

1. **Write the recipe** — create `catalog/<source>.json`. At minimum include
   `api.base_url`, `cli_parameters.required`, and an `output_schema`. Copy an
   existing recipe (e.g. `catalog/worldbank.json`) as a template.

2. **Write the fetcher** — create `sources/<source>.py` with:
   ```python
   from sources.base import get, log, parse_comma_list

   def fetch(recipe, params):
       base_url = recipe["api"]["base_url"]
       rows = []
       # ... call the API via get(url), build dict rows ...
       return rows  # list[dict]; the dict keys become CSV columns
   ```
   Reuse `sources/base.py` (`get()` already handles retries/backoff/timeouts).

3. **Register it** — add one tuple to `_SOURCE_SPECS` in
   [`sources/__init__.py`](sources/__init__.py):
   ```python
   ("<source>", "<module_name>", "fetch"),
   ```
   Optionally add an entry to `catalog/index.json` so it's discoverable.

The import in `sources/__init__.py` is lazy and wrapped in try/except, so a
missing optional dependency disables only that one source — `--help` and the
other sources keep working.

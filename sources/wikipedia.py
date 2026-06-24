"""Wikipedia Pageviews API fetcher."""

import time
from datetime import datetime

from sources.base import get, log, parse_comma_list


def _to_yyyymmdd(date_str):
    """Convert YYYY-MM-DD to YYYYMMDD."""
    if not date_str or date_str == "today":
        return datetime.now().strftime("%Y%m%d")
    return date_str.replace("-", "")


def fetch(recipe, params):
    articles = parse_comma_list(params.get("articles"))
    if not articles:
        raise ValueError("--articles is required for wikipedia source")

    # Use `or default` rather than dict.get(key, default): the CLI always
    # passes every param key, so unset options arrive as None (key present,
    # value None) and would slip past a get() default.
    start = _to_yyyymmdd(params.get("start") or "2015-07-01")
    end = _to_yyyymmdd(params.get("end") or "today")
    base_url = recipe["api"]["base_url"]
    all_rows = []

    for page in articles:
        url = (
            f"{base_url}/per-article/en.wikipedia/all-access/all-agents/"
            f"{page}/daily/{start}/{end}"
        )
        try:
            r = get(url, timeout=15)
            items = r.json().get("items", [])

            for item in items:
                ts = item["timestamp"]
                all_rows.append({
                    "article": page,
                    "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                    "views": item["views"],
                    "project": "en.wikipedia",
                    "access": "all-access",
                    "agent": "all-agents",
                })

            log(f"  {page}: {len(items)} records")
            time.sleep(0.5)

        except Exception as e:
            log(f"  {page}: {e}")

    return all_rows

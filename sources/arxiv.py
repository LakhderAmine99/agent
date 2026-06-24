"""arXiv API fetcher."""

import time

import feedparser

from sources.base import log


def _build_search_query(category, keyword):
    parts = []
    if category:
        parts.append(f"cat:{category}")
    if keyword:
        parts.append(f"abs:{keyword}")
    if not parts:
        return "all:*"
    return "+AND+".join(parts)


def fetch(recipe, params):
    category = params.get("category")
    keyword = params.get("keyword")
    start_date = params.get("start")
    max_results = int(params.get("max_results", 100))
    base_url = recipe["api"]["base_url"]

    search_query = _build_search_query(category, keyword)
    all_rows = []
    fetched = 0
    offset = 0
    page_size = min(max_results, 2000)

    while fetched < max_results:
        batch = min(page_size, max_results - fetched)
        url = (
            f"{base_url}/query?search_query={search_query}"
            f"&start={offset}&max_results={batch}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                break

            for entry in feed.entries:
                submitted = entry.get("published", "")[:10]
                if start_date and submitted < start_date:
                    continue

                authors = " | ".join(
                    a.name for a in entry.get("authors", [])[:5]
                )
                categories = " | ".join(
                    t.get("term", "") for t in entry.get("tags", [])
                )
                primary = getattr(
                    entry, "arxiv_primary_category", {}
                ).get("term", category or "")

                all_rows.append({
                    "arxiv_id": entry.id.split("/")[-1],
                    "title": entry.title.replace("\n", " ").strip(),
                    "abstract": entry.summary.replace("\n", " ").strip()[:500],
                    "submitted_date": submitted,
                    "updated_date": entry.get("updated", "")[:10],
                    "primary_category": primary,
                    "all_categories": categories,
                    "title_word_count": len(entry.title.split()),
                    "abstract_word_count": len(entry.summary.split()),
                    "authors": authors,
                })

            fetched += len(feed.entries)
            offset += len(feed.entries)
            log(f"  fetched {len(all_rows)} papers so far")
            time.sleep(3)

            if len(feed.entries) < batch:
                break

        except Exception as e:
            log(f"  arxiv: {e}")
            break

    return all_rows

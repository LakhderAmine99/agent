"""Source fetchers for the data agent.

Each fetcher is imported lazily so that a missing optional dependency
(e.g. feedparser for arxiv) only disables that one source instead of
crashing the entire CLI — including --help.
"""

import sys

# (source id, module name, attribute holding the fetch callable)
_SOURCE_SPECS = [
    ("wikipedia", "wikipedia", "fetch"),
    ("imf", "imf", "fetch"),
    ("worldbank", "worldbank", "fetch"),
    ("arxiv", "arxiv", "fetch"),
    ("ofac", "ofac", "fetch"),
]

FETCHERS = {}

for _source_id, _module_name, _attr in _SOURCE_SPECS:
    try:
        _module = __import__(f"sources.{_module_name}", fromlist=[_attr])
        FETCHERS[_source_id] = getattr(_module, _attr)
    except ImportError as exc:
        print(
            f"Warning: source '{_source_id}' unavailable "
            f"(missing dependency: {exc})",
            file=sys.stderr,
        )

del _source_id, _module_name, _attr

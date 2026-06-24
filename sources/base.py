"""Shared HTTP helpers for all source fetchers."""

import sys
import time

import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def log(msg):
    """Print status to stderr so stdout stays clean for --stdout-json."""
    print(msg, file=sys.stderr)


def get(url, headers=None, timeout=30, retries=3, params=None):
    """GET with retry on 503 and rate-limit backoff on 429."""
    headers = {**DEFAULT_HEADERS, **(headers or {})}

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, params=params)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60))
                log(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            if r.status_code == 503 and attempt < retries - 1:
                log(f"  Server busy (503). Retry {attempt + 1}/{retries}...")
                time.sleep(60)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise

    return None


def parse_comma_list(value):
    """Split comma-separated CLI value into stripped list."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def parse_filter(value):
    """Parse filter string like 'program=RUSSIA,sdn_type=Individual' into dict."""
    if not value:
        return {}
    result = {}
    for part in value.split(","):
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            result[key.strip()] = val.strip()
    return result

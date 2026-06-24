"""IMF DataMapper API fetcher."""

import time

import requests

from sources.base import DEFAULT_HEADERS, log, parse_comma_list

try:
    import pycountry
except ImportError:
    pycountry = None

IMF_WARMUP_URL = "https://www.imf.org/en/Data"

# Note surfaced in the output when the API blocks automated requests.
BLOCKED_NOTE = (
    "IMF API currently blocking automated requests. "
    "Use --source worldbank for overlapping indicators."
)

INDICATOR_NAMES = {
    "NGDP_RPCH": "GDP Growth Rate %",
    "PCPIPCH": "Inflation Rate %",
    "LUR": "Unemployment Rate %",
    "BCA_NGDPD": "Current Account % GDP",
    "GGXWDG_NGDP": "Government Debt % GDP",
    "NGDPDPC": "GDP per Capita USD",
}

# Fallback ISO2 -> ISO3 map used only when pycountry is not installed.
ISO2_TO_ISO3 = {
    "US": "USA", "GB": "GBR", "DE": "DEU", "FR": "FRA", "JP": "JPN",
    "CN": "CHN", "IN": "IND", "BR": "BRA", "CA": "CAN", "AU": "AUS",
    "KR": "KOR", "MX": "MEX", "RU": "RUS", "ZA": "ZAF", "IT": "ITA",
    "ES": "ESP", "NL": "NLD", "SE": "SWE", "CH": "CHE", "NO": "NOR",
}


def _to_imf_country(code):
    """Map an ISO2 country code to the ISO3 code IMF DataMapper uses.

    Uses pycountry for full coverage when available, otherwise falls back
    to the hardcoded map. Unknown codes are returned uppercased as-is
    (allows passing an ISO3 code directly).
    """
    code = code.upper()
    if pycountry is not None:
        match = pycountry.countries.get(alpha_2=code)
        if match is not None:
            return match.alpha_3
    return ISO2_TO_ISO3.get(code, code)


def _year_in_range(year, start, end):
    try:
        y = int(year)
    except (ValueError, TypeError):
        return False
    if start and y < int(start):
        return False
    if end and end != "present" and y > int(end):
        return False
    return True


def _imf_get(url, session, timeout=30):
    """GET from IMF DataMapper API using a warmed-up session."""
    for attempt in range(3):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 403 and attempt == 0:
                session.get(IMF_WARMUP_URL, timeout=15)
                continue
            if r.status_code == 503 and attempt < 2:
                log("  IMF server busy, retrying...")
                time.sleep(60)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError:
            if attempt < 2:
                time.sleep(5)
                continue
            raise
    return None


def fetch(recipe, params):
    indicators = parse_comma_list(params.get("indicators"))
    if not indicators:
        raise ValueError("--indicators is required for imf source")

    countries = parse_comma_list(params.get("countries"))
    # `or default`, not get(key, default): the CLI always passes the key with
    # value None when the option is unset, which would slip past a get() default.
    start = params.get("start") or "2000"
    end = params.get("end") or "present"
    base_url = recipe["api"]["base_url"]
    all_rows = []
    forbidden = False

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    # Headers that help get past IMF's automated-request blocking.
    session.headers["Referer"] = "https://www.imf.org/"
    session.headers["Accept"] = "application/json"

    # Warm up the session, then pause before the first API request so the
    # server has registered the warm-up hit.
    session.get(IMF_WARMUP_URL, timeout=15)
    time.sleep(2)

    for code in indicators:
        name = INDICATOR_NAMES.get(code, code)
        url = f"{base_url}/{code}"
        rows, blocked = _fetch_indicator(
            url, code, name, countries, start, end, session
        )
        all_rows.extend(rows)
        forbidden = forbidden or blocked
        time.sleep(1)

    # If the API blocked us and we got nothing back, surface a note in the
    # output so the user knows why and what to do instead.
    if forbidden and not all_rows:
        log(f"\n{BLOCKED_NOTE}")
        all_rows.append({
            "country": None,
            "indicator_code": None,
            "indicator_name": None,
            "year": None,
            "value": None,
            "note": BLOCKED_NOTE,
        })

    return all_rows


def _fetch_indicator(url, code, name, country_filter, start, end, session):
    """Return (rows, forbidden) for one indicator. forbidden=True on HTTP 403."""
    rows = []
    try:
        r = _imf_get(url, session, timeout=30)
        values = r.json().get("values", {}).get(code, {})

        filter_codes = None
        if country_filter and "all" not in [c.lower() for c in country_filter]:
            filter_codes = {_to_imf_country(c) for c in country_filter}

        for country, years in values.items():
            if filter_codes and country not in filter_codes:
                continue
            for year, value in years.items():
                if value is not None and _year_in_range(year, start, end):
                    rows.append({
                        "country": country,
                        "indicator_code": code,
                        "indicator_name": name,
                        "year": year,
                        "value": value,
                    })

        log(f"  {code}: {len(rows)} records")
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            log(f"  {code}: access forbidden (IMF may be blocking automated requests)")
            return rows, True
        log(f"  {code}: {e}")
    except Exception as e:
        log(f"  {code}: {e}")

    return rows, False

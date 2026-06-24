"""World Bank Indicators API fetcher."""

import time

from sources.base import get, log, parse_comma_list

INDICATOR_NAMES = {
    "NY.GDP.MKTP.KD.ZG": "GDP Growth Rate %",
    "NY.GDP.MKTP.CD": "GDP (current USD)",
    "FP.CPI.TOTL.ZG": "Inflation CPI %",
    "SL.UEM.TOTL.ZS": "Unemployment % labor force",
    "GC.DOD.TOTL.GD.ZS": "Government Debt % GDP",
    "NY.GDP.PCAP.CD": "GDP per Capita (USD)",
    "SP.POP.TOTL": "Total Population",
    "BX.KLT.DINV.WD.GD.ZS": "FDI Inflows % GDP",
    "NE.TRD.GNFS.ZS": "Trade % of GDP",
    "BN.CAB.XOKA.GD.ZS": "Current Account % GDP",
}


def fetch(recipe, params):
    indicators = parse_comma_list(params.get("indicators"))
    if not indicators:
        raise ValueError("--indicators is required for worldbank source")

    # Use `or default` rather than dict.get(key, default): the CLI always
    # passes every param key, so unset options arrive as None (key present,
    # value None) and would slip past a get() default.
    countries_raw = params.get("countries") or "all"
    if countries_raw.lower() == "all":
        countries = "all"
    else:
        countries = ";".join(parse_comma_list(countries_raw))

    start = params.get("start") or "2000"
    end = params.get("end") or "present"
    if end == "present":
        end = str(time.localtime().tm_year)

    base_url = recipe["api"]["base_url"]
    all_rows = []

    for code in indicators:
        name = INDICATOR_NAMES.get(code, code)
        page = 1
        count = 0

        while True:
            url = (
                f"{base_url}/country/{countries}/indicator/{code}"
                f"?format=json&date={start}:{end}&per_page=20000&page={page}"
            )
            try:
                r = get(url, timeout=60)
                data = r.json()

                if len(data) < 2 or not data[1]:
                    break

                for rec in data[1]:
                    if rec.get("value") is not None:
                        all_rows.append({
                            "country_code": rec["country"]["id"],
                            "country_name": rec["country"]["value"],
                            "indicator_code": code,
                            "indicator_name": name,
                            "year": rec["date"],
                            "value": rec["value"],
                        })
                        count += 1

                meta = data[0]
                if page >= meta.get("pages", 1):
                    break
                page += 1
                time.sleep(1)

            except Exception as e:
                log(f"  {code}: {e}")
                break

        log(f"  {name}: {count} records")
        time.sleep(1)

    return all_rows

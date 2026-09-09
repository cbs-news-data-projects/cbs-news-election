"""Fetch CBS News House race ratings and flatten to one row per race.

Source: CBS News Elections, preelection race ratings. 2026 general election, House.
https://partners.elections.cbsnews.com/live/2026G/preelection/H/races
Input:  none, pulled directly from the source
Output: data/processed/house_races.csv
Run:    uv run python scripts/fetch.py

Runs locally or on a schedule via .github/workflows/data-fetch.yml.
"""

import requests

from config import PROCESSED_DATA_DIR

URL = "https://partners.elections.cbsnews.com/live/2026G/preelection/H/races"


def flatten_race(race: dict) -> dict:
    row = {
        "key": race.get("key"),
        "state": race.get("state"),
        "state_code": race.get("stateCode"),
        "district": race.get("district"),
        # 4-digit state FIPS + district number. Matches Datawrapper's
        # congressional district map key more reliably than district text.
        "geo_id": race.get("geoId"),
        "rating": race.get("rating"),
        "incumbent_party": race.get("incumbentParty"),
        "is_battleground": race.get("isBattleground"),
        "is_key_race": race.get("keyRace"),
    }

    # Keys by party (DEM/REP). A candidate of another party lands in
    # other_candidate instead, so a jungle-primary or third-party race
    # does not silently overwrite a major-party column.
    other_candidates = []
    for candidate in race.get("candidates", []):
        party = candidate.get("party")
        name = candidate.get("fullName")
        pct = candidate.get("estPct")
        if party == "DEM":
            row["dem_candidate"] = name
            row["dem_pct"] = pct
        elif party == "REP":
            row["rep_candidate"] = name
            row["rep_pct"] = pct
        else:
            other_candidates.append(f"{name} ({party})")

    row["other_candidates"] = "; ".join(other_candidates) if other_candidates else None
    return row


def fetch() -> None:
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    races = resp.json()

    import pandas as pd

    df = pd.DataFrame(flatten_race(race) for race in races)

    # Datawrapper's congressional district maps join on this field. A
    # malformed geo_id breaks the map silently instead of raising an error.
    bad_geo_id = df[~df["geo_id"].astype(str).str.match(r"^\d{4}$")]
    if len(bad_geo_id):
        raise ValueError(
            f"{len(bad_geo_id)} race(s) have a missing or malformed geo_id: "
            f"{bad_geo_id['key'].tolist()}"
        )

    out_path = PROCESSED_DATA_DIR / "house_races.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(df):,} races)")


if __name__ == "__main__":
    fetch()

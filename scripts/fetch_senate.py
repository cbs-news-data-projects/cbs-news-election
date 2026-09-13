"""Fetch CBS News Senate race ratings and export a flat race-level table.

Source: CBS News Elections, preelection race ratings. 2026 general election, Senate.
https://www.cbsnews.com/election-api/2026/pre-election-senate-races.json
Input:  none, pulled directly from the source
Output: data/raw/senate_races.json (raw API response, overwritten each run)
        data/processed/senate_races.csv
        data/processed/senate_battleground.csv (races where is_battleground is True)
Run:    uv run python scripts/fetch_senate.py

Public feed, no VPN required. Replaces the old partners.elections.cbsnews.com
feed. Candidate names/percentages aren't needed downstream, so this only
keeps race-level rating fields. This script skips district and geo_id logic.
Senate races are one per state.

Fetches via the `curl` binary, not a Python HTTP client: CBS's edge
consistently 406s requests from Python's ssl stack (both requests and
httpx, HTTP/1.1 or HTTP/2) by TLS fingerprint, while curl is never blocked.
"""

import json
import subprocess

import pandas as pd

from config import PROCESSED_DATA_DIR, RAW_DATA_DIR

URL = "https://www.cbsnews.com/election-api/2026/pre-election-senate-races.json"


def flatten_race(race: dict) -> dict:
    return {
        "key": race.get("key"),
        "state": race.get("state"),
        "state_code": race.get("stateCode"),
        "rating": race.get("rating"),
        "incumbent_party": race.get("incumbentParty"),
        "is_battleground": race.get("isBattleground"),
        "is_key_race": race.get("keyRace"),
    }


def fetch() -> None:
    result = subprocess.run(
        ["curl", "-s", "-m", "30", "--fail", URL],
        capture_output=True, text=True, check=True,
    )
    raw_path = RAW_DATA_DIR / "senate_races.json"
    raw_path.write_text(result.stdout)

    races = json.loads(result.stdout)["senate-races"]

    df = pd.DataFrame(flatten_race(race) for race in races)

    out_path = PROCESSED_DATA_DIR / "senate_races.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(df):,} races)")

    battleground_path = PROCESSED_DATA_DIR / "senate_battleground.csv"
    df[df["is_battleground"]].to_csv(battleground_path, index=False)
    print(f"Wrote {battleground_path} ({len(df[df['is_battleground']]):,} races)")


if __name__ == "__main__":
    fetch()

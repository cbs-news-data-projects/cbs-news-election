"""Fetch CBS News Senate race ratings and export a flat race-level table.

Source: CBS News Elections, preelection race ratings. 2026 general election, Senate.
https://www.cbsnews.com/election-api/2026/pre-election-senate-races.json
Input:  none, pulled directly from the source
Output: data/raw/senate_races_<UTC timestamp>.json (raw API response;
        keeps the last RAW_SNAPSHOTS_TO_KEEP runs so rating changes can be
        diffed between snapshots, older ones pruned automatically)
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
from datetime import datetime, timezone

import pandas as pd

from config import PROCESSED_DATA_DIR, RAW_DATA_DIR

URL = "https://www.cbsnews.com/election-api/2026/pre-election-senate-races.json"
RAW_SNAPSHOTS_TO_KEEP = 5


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


def report_changes(previous_df: pd.DataFrame, current_df: pd.DataFrame) -> None:
    previous_by_key = previous_df.set_index("key")
    current_by_key = current_df.set_index("key")

    added = current_by_key.index.difference(previous_by_key.index)
    removed = previous_by_key.index.difference(current_by_key.index)
    shared = current_by_key.index.intersection(previous_by_key.index)
    changed = shared[
        (previous_by_key.loc[shared].values != current_by_key.loc[shared].values).any(axis=1)
    ]

    if added.empty and removed.empty and changed.empty:
        print("No change from previous senate_races.csv")
        return

    print(f"CHANGED from previous senate_races.csv: {len(changed)} changed, {len(added)} added, {len(removed)} removed")
    for key in changed:
        before, after = previous_by_key.loc[key], current_by_key.loc[key]
        diffs = [f"{col}: {before[col]!r} -> {after[col]!r}" for col in current_by_key.columns if before[col] != after[col]]
        print(f"  {key} ({after['state']}): {'; '.join(diffs)}")
    for key in added:
        print(f"  + {key} ({current_by_key.loc[key, 'state']})")
    for key in removed:
        print(f"  - {key} ({previous_by_key.loc[key, 'state']})")


def fetch() -> None:
    result = subprocess.run(
        ["curl", "-s", "-m", "30", "--fail", URL],
        capture_output=True, text=True, check=True,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = RAW_DATA_DIR / f"senate_races_{timestamp}.json"
    raw_path.write_text(result.stdout)

    old_snapshots = sorted(RAW_DATA_DIR.glob("senate_races_*.json"))
    for stale_path in old_snapshots[:-RAW_SNAPSHOTS_TO_KEEP]:
        stale_path.unlink()

    races = json.loads(result.stdout)["senate-races"]

    df = pd.DataFrame(flatten_race(race) for race in races)

    out_path = PROCESSED_DATA_DIR / "senate_races.csv"
    previous_df = pd.read_csv(out_path) if out_path.exists() else None
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(df):,} races)")
    if previous_df is not None:
        report_changes(previous_df, df)

    battleground_path = PROCESSED_DATA_DIR / "senate_battleground.csv"
    df[df["is_battleground"]].to_csv(battleground_path, index=False)
    print(f"Wrote {battleground_path} ({len(df[df['is_battleground']]):,} races)")


if __name__ == "__main__":
    fetch()

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

senate_battleground.csv is the one file in data/processed/ that git tracks.
A .gitignore exception publishes it for this raw GitHub URL:
https://raw.githubusercontent.com/cbs-news-data-projects/cbs-news-election/refs/heads/main/data/processed/senate_battleground.csv
senate_races.csv stays local.

Each run overwrites both CSVs. The printed feed timestamp is the pull date
of record. The feed holds one row per Senate seat up in 2026, one or two
per state.

Public feed, no VPN required. It is separate from the dev-fly Election
Night feeds that scripts/fetch.py reads. It keeps race-level rating fields
only. Candidate names and percentages are not used downstream.

Fetches via the `curl` binary, not a Python HTTP client: CBS's edge
consistently 406s requests from Python's ssl stack (both requests and
httpx, HTTP/1.1 or HTTP/2) by TLS fingerprint, while curl is never blocked.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402

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
    # CBS News preelection Senate ratings feed, pulled live on every run.
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

    feed = json.loads(result.stdout)
    races = feed["senate-races"]

    df = pd.DataFrame(flatten_race(race) for race in races)

    out_path = PROCESSED_DATA_DIR / "senate_races.csv"
    previous_df = pd.read_csv(out_path) if out_path.exists() else None
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(df):,} races)")
    if previous_df is not None:
        report_changes(previous_df, df)

    battleground = df[df["is_battleground"]]
    battleground_path = PROCESSED_DATA_DIR / "senate_battleground.csv"
    battleground.to_csv(battleground_path, index=False)
    print(f"Wrote {battleground_path} ({len(battleground):,} races)")

    ratings = "; ".join(f"{r.state} {r.rating}" for r in battleground.itertuples())
    print(f"""
SUMMARY
Records:  {len(df):,} Senate races | feed timestamp {feed["meta"]["timestamp"]} | pulled {timestamp}
Findings: {len(battleground):,} races are battlegrounds: {ratings}
Concerns: The feed sets is_battleground and rating. This script does not change them.
Outputs:  {out_path.relative_to(PROCESSED_DATA_DIR.parent.parent)}, {battleground_path.relative_to(PROCESSED_DATA_DIR.parent.parent)}
""")


if __name__ == "__main__":
    fetch()

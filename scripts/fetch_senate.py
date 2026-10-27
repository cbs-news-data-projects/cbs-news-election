"""Write the Senate battleground table for the Datawrapper map.

Source: CBS News Elections, cached Election Night feeds. 2026 general election.
        https://dev-fly.cbsnews.com/election-api/2026/general-races.json
        https://dev-fly.cbsnews.com/election-api/2026/general-balance.json
Input:  none, pulled directly from the source. Requires the CBS VPN.
Output: data/raw/<pull time>/general-races.json, general-balance.json
        (untouched snapshots, not versioned)
        data/processed/senate_battleground.csv  one row per Senate race the
        feed marks as a battleground
Run:    uv run python scripts/fetch_senate.py

senate_battleground.csv is the one file in data/processed/ that git tracks.
A .gitignore exception publishes it for the Datawrapper map at:
https://raw.githubusercontent.com/cbs-news-data-projects/cbs-news-election/refs/heads/main/data/processed/senate_battleground.csv

Each run overwrites the CSV. The map matches rows on state_code and colors
them by rating. The feed sets rating and is_battleground. This script does
not change them. A race with no rating in the feed has a blank rating cell.

The script stops before it writes the CSV if dev-fly is unreachable, or if
the Senate race count differs from the seats at stake in the balance file.
The published CSV stays intact after a failed pull.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from scripts.fetch import BASE_URL, get_json, save_raw  # noqa: E402

OUT_PATH = PROCESSED_DATA_DIR / "senate_battleground.csv"

# Column names match the CSV the Datawrapper map already reads.
COLUMNS = {
    "key": "key",
    "stateName": "state",
    "stateCode": "state_code",
    "rating": "rating",
    "incumbentParty": "incumbent_party",
    "isBattleground": "is_battleground",
}


def report_changes(previous, current):
    """Prints battleground races added, removed, or re-rated since the last run."""
    before = previous.set_index("key")["rating"]
    after = current.set_index("key")["rating"]
    added = after.index.difference(before.index)
    removed = before.index.difference(after.index)
    shared = after.index.intersection(before.index)
    changed = [k for k in shared if str(before[k]) != str(after[k])]
    if not (len(added) or len(removed) or changed):
        print("No change from the published CSV.")
        return
    print(f"CHANGED from the published CSV: {len(changed)} re-rated, {len(added)} added, {len(removed)} removed")
    for k in changed:
        print(f"  {k}: {before[k]} -> {after[k]}")
    for k in added:
        print(f"  + {k} ({after[k]})")
    for k in removed:
        print(f"  - {k}")


def main():
    pulled = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        # CBS cached Election Night feeds on dev-fly, pulled on every run.
        races_feed = get_json(f"{BASE_URL}/general-races.json")
        balance = get_json(f"{BASE_URL}/general-balance.json")
    except (requests.ConnectionError, requests.Timeout) as err:
        sys.exit(f"STOP: cannot reach dev-fly. Connect to the VPN and rerun. No CSV written.\n{err}")

    raw_dir = RAW_DATA_DIR / pulled
    raw_dir.mkdir(parents=True, exist_ok=True)
    save_raw(races_feed, raw_dir, "general-races")
    save_raw(balance, raw_dir, "general-balance")

    # Senate races by state. The US row is the national Senate placeholder,
    # not a seat, so the count check leaves it out.
    senate = [r for r in races_feed["races"] if r["office"] == "S" and r["stateCode"] != "US"]
    seats = next(o["seatsAtStake"] for o in balance["balance"]["offices"] if o["name"] == "S")
    if len(senate) != seats:
        sys.exit(f"STOP: {len(senate)} Senate races in the feed, {seats} seats at stake. No CSV written.")

    df = pd.DataFrame(senate)[list(COLUMNS)].rename(columns=COLUMNS)
    battleground = df[df["is_battleground"]]

    previous = pd.read_csv(OUT_PATH) if OUT_PATH.exists() else None
    battleground.to_csv(OUT_PATH, index=False)
    if previous is not None:
        report_changes(previous, battleground)

    unrated = battleground.loc[battleground["rating"].isna(), "state"].tolist()
    ratings = "; ".join(f"{r.state} {r.rating}" for r in battleground.itertuples())
    print(f"""
SUMMARY
Records:  {len(df):,} Senate races | {len(battleground):,} battlegrounds | feed timestamp {races_feed["meta"]["timestamp"]} | pulled {pulled}
Findings: {ratings}
Concerns: No rating in the feed: {", ".join(unrated) or "none"}
Outputs:  data/processed/senate_battleground.csv
""")


if __name__ == "__main__":
    main()

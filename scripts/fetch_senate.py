"""Write the Senate battleground table for the Datawrapper map.

Source: CBS News Elections, preelection Senate race ratings. 2026 general election.
        https://www.cbsnews.com/election-api/2026/pre-election-senate-races.json
Input:  none, pulled directly from the source
Output: data/raw/<pull time>/pre-election-senate-races.json
        (untouched snapshot, not versioned)
        data/processed/senate_battleground.csv  one row per Senate race the
        feed marks as a battleground
Run:    uv run python scripts/fetch_senate.py

This script uses the preelection feed through Election Day, Nov. 3, 2026.
As of 2026-10-27, dev-fly holds Win ratings, vote counts and race calls,
so it does not feed the map before then.

senate_battleground.csv is the one file in data/processed/ that git tracks.
A .gitignore exception publishes it for the Datawrapper map at:
https://raw.githubusercontent.com/cbs-news-data-projects/cbs-news-election/refs/heads/main/data/processed/senate_battleground.csv

Each run overwrites the CSV. The map matches rows on state_code and colors
them by rating. The feed sets rating, is_battleground and is_key_race. This
script does not change them.

Downloads with the curl binary. The www.cbsnews.com edge rejects Python
HTTP clients with an HTTP 406.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import API_TIMEOUT, PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402

URL = "https://www.cbsnews.com/election-api/2026/pre-election-senate-races.json"
OUT_PATH = PROCESSED_DATA_DIR / "senate_battleground.csv"

# Column names match the CSV the Datawrapper map reads.
COLUMNS = {
    "key": "key",
    "state": "state",
    "stateCode": "state_code",
    "rating": "rating",
    "incumbentParty": "incumbent_party",
    "isBattleground": "is_battleground",
    "keyRace": "is_key_race",
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
    # CBS preelection Senate ratings feed, downloaded on every run.
    out = subprocess.run(
        ["curl", "-sSf", "--max-time", str(API_TIMEOUT), URL],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"STOP: cannot download the preelection feed. No CSV written.\n{out.stderr}")
    feed = json.loads(out.stdout)

    raw_dir = RAW_DATA_DIR / pulled
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "pre-election-senate-races.json").write_text(out.stdout)

    df = pd.DataFrame(feed["senate-races"])[list(COLUMNS)].rename(columns=COLUMNS)
    battleground = df[df["is_battleground"]]

    previous = pd.read_csv(OUT_PATH) if OUT_PATH.exists() else None
    battleground.to_csv(OUT_PATH, index=False)
    if previous is not None:
        report_changes(previous, battleground)

    ratings = "; ".join(f"{r.state} {r.rating}" for r in battleground.itertuples())
    print(f"""
SUMMARY
Records:  {len(df):,} Senate races | {len(battleground):,} battlegrounds | feed timestamp {feed["meta"]["timestamp"]} | pulled {pulled}
Findings: {ratings}
Concerns: The feed timestamp is the last time CBS updated these ratings.
Outputs:  data/processed/senate_battleground.csv
""")


if __name__ == "__main__":
    main()

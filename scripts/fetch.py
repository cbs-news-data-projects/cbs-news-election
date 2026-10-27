"""Pull the CBS News 2026 general election feeds and write flat CSVs.

Source: CBS News Elections, cached Election Night feeds. 2026 general election.
        https://dev-fly.cbsnews.com/election-api/2026/general-balance.json
        https://dev-fly.cbsnews.com/election-api/2026/general-races.json
        https://dev-fly.cbsnews.com/election-api/2026/general-races-{xx}.json
Input:  none, pulled directly from the source
Output: data/raw/<pull time>/*.json (untouched snapshots, not versioned)
        data/processed/balance.csv          one row per chamber and party
        data/processed/balance_ratings.csv  one row per chamber and rating
        data/processed/races.csv            one row per race
        data/processed/candidates.csv       one row per candidate, race fields attached
Run:    uv run python scripts/fetch.py
        uv run python scripts/fetch.py --check-states  (adds the state file comparison)

The all-races file is the only source for races.csv and candidates.csv.
The 51 state files (50 states plus DC) held the same races, field for
field, on 2026-10-13. They contain no extra data. The national House
popular-vote row (state code US) exists only in the all-races file.

--check-states downloads the state files and compares them against the
all-races file. It reports which copy of each differing race is newer. It
never changes the CSVs. A mismatch prints a warning and does not stop the run.

The script stops before it writes any CSV if a state is missing or a
chamber's race count differs from the seats at stake in the balance file.
The CSVs on disk stay intact after a failed pull.
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import API_TIMEOUT, PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402

BASE_URL = "https://dev-fly.cbsnews.com/election-api/2026"

# 50 states plus DC. Each has a general-races-{xx}.json file. US is not a
# state file. It is the national House row inside general-races.json.
STATE_CODES = [
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI",
    "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN",
    "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA",
    "WI", "WV", "WY",
]

# Display fields for the CBS web graphics. They carry no reporting value.
DROP_FIELDS = {"color", "color2", "ratingColor", "ratingCandidateColor", "img"}

# Feed office codes for the chambers in general-balance.json.
CHAMBERS = {"S": "Senate", "G": "Governor", "H": "House"}


def snake(name):
    """Converts a camelCase feed key to snake_case."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def get_json(url):
    """Downloads one dev-fly feed file and returns the parsed JSON."""
    resp = requests.get(url, timeout=API_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def save_raw(payload, folder, name):
    """Writes the feed file to the raw snapshot folder as received."""
    (folder / f"{name}.json").write_text(json.dumps(payload))


def balance_tables(balance):
    """Flattens general-balance.json into a party table and a ratings table."""
    feed_time = balance["meta"]["timestamp"]
    party_rows, rating_rows = [], []
    for office in balance["balance"]["offices"]:
        chamber = {
            "chamber": CHAMBERS.get(office["name"], office["name"]),
            "seats_total": office["seatsTotal"],
            "seats_at_stake": office["seatsAtStake"],
            "seats_for_majority": office["seatsNeedForMajority"],
            "last_updated": office["lastUpdated"],
        }
        for party in office["parties"]:
            row = {k: v for k, v in party.items() if k not in DROP_FIELDS}
            row = {snake(k): v for k, v in row.items()}
            name = {"party": row.pop("name")}
            party_rows.append({**chamber, **name, **row, "feed_timestamp": feed_time})
        for rating, seats in office["ratings"].items():
            rating_rows.append({
                "chamber": chamber["chamber"],
                "rating": rating,
                "seats": seats,
                "feed_timestamp": feed_time,
            })
    return pd.DataFrame(party_rows), pd.DataFrame(rating_rows)


def race_tables(races, feed_time):
    """Splits the race list into a race table and a candidate table."""
    race_rows, cand_rows = [], []
    for race in races:
        fields = {
            snake(k): v for k, v in race.items()
            if k != "candidates" and k not in DROP_FIELDS
        }
        fields["race_id"] = fields.pop("id")
        fields["race_key"] = fields.pop("key")
        # Postal code plus two-digit district, e.g. PA-07. House races only.
        fields["district_label"] = (
            f"{race['stateCode']}-{race['jurisdictionCode']:02d}"
            if race["jType"] == "CD" else None
        )
        fields["n_candidates"] = len(race["candidates"])
        fields["feed_timestamp"] = feed_time
        race_rows.append(fields)

        for order, cand in enumerate(race["candidates"], start=1):
            c = {snake(k): v for k, v in cand.items() if k not in DROP_FIELDS}
            c["candidate_id"] = c.pop("id")
            # Position in the feed's candidate list. The feed orders by vote
            # once results arrive.
            c["feed_order"] = order
            cand_rows.append({**fields, **c})

    race_df = pd.DataFrame(race_rows)
    cand_df = pd.DataFrame(cand_rows)
    lead = ["race_id", "state_code", "office", "office_name", "district_label"]
    race_df = race_df[lead + [c for c in race_df.columns if c not in lead]]
    cand_lead = lead + ["candidate_id", "full_name", "party", "is_incumbent"]
    cand_df = cand_df[cand_lead + [c for c in cand_df.columns if c not in cand_lead]]
    return race_df, cand_df


def check_completeness(races, balance):
    """Stops the run if a state or a chamber's races are missing."""
    present = {r["stateCode"] for r in races}
    missing = sorted(set(STATE_CODES) - present)
    if missing:
        sys.exit(f"STOP: no races for {', '.join(missing)}. No CSVs written.")

    # House counts district races only. The national popular-vote row
    # (jType NR) is not a seat.
    for office in balance["balance"]["offices"]:
        code = office["name"]
        n = sum(
            1 for r in races
            if r["office"] == code and (code != "H" or r["jType"] == "CD")
        )
        if n != office["seatsAtStake"]:
            sys.exit(
                f"STOP: {CHAMBERS[code]} has {n} races in the feed but "
                f"{office['seatsAtStake']} seats at stake. No CSVs written."
            )


def compare_state_files(all_races, state_payloads):
    """Prints any difference between the combined state files and the all-races file.

    For a race that differs, the copy with the later lastUpdated time is the
    newer one. The tally answers which file leads on Election Night.
    """
    full = {r["id"]: r for r in all_races["races"] if r["stateCode"] != "US"}
    combined = {
        r["id"]: r
        for code, payload in state_payloads.items()
        for r in payload[code.lower()]
    }
    stamps = sorted(p["meta"]["timestamp"] for p in state_payloads.values())
    print(f"All-races file timestamp:   {all_races['meta']['timestamp']}")
    print(f"State file timestamps:      {stamps[0]} to {stamps[-1]}")

    only_full = sorted(set(full) - set(combined))
    only_states = sorted(set(combined) - set(full))
    changed = sorted(i for i in set(full) & set(combined) if full[i] != combined[i])
    if not (only_full or only_states or changed):
        print(f"State files match the all-races file: {len(combined)} races.")
        return

    # ISO 8601 strings in one format sort in time order.
    state_newer = sum(combined[i]["lastUpdated"] > full[i]["lastUpdated"] for i in changed)
    full_newer = sum(combined[i]["lastUpdated"] < full[i]["lastUpdated"] for i in changed)
    states_hit = sorted({full[i]["stateCode"] for i in changed})
    print("WARNING: state files differ from the all-races file.")
    print(f"  In all-races only:    {len(only_full)} {only_full[:10]}")
    print(f"  In state files only:  {len(only_states)} {only_states[:10]}")
    print(f"  Same race, different content: {len(changed)} in {', '.join(states_hit)}")
    print(f"    State copy newer:     {state_newer}")
    print(f"    All-races copy newer: {full_newer}")
    print(f"    Same update time:     {len(changed) - state_newer - full_newer}")
    print("  The CSVs use the all-races file. See README, 'State file check'.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check-states", action="store_true",
        help="Also download the 51 state files and compare them to the all-races file.",
    )
    args = parser.parse_args()

    pulled = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = RAW_DATA_DIR / pulled
    raw_dir.mkdir(parents=True)

    balance = get_json(f"{BASE_URL}/general-balance.json")
    save_raw(balance, raw_dir, "general-balance")
    all_races = get_json(f"{BASE_URL}/general-races.json")
    save_raw(all_races, raw_dir, "general-races")
    races = all_races["races"]

    check_completeness(races, balance)

    if args.check_states:
        # Eight parallel downloads. One at a time takes about 45 seconds.
        urls = [f"{BASE_URL}/general-races-{c.lower()}.json" for c in STATE_CODES]
        with ThreadPoolExecutor(max_workers=8) as pool:
            payloads = list(pool.map(get_json, urls))
        # Each state file keys its race list by the lowercase postal code.
        state_payloads = dict(zip(STATE_CODES, payloads))
        for code, payload in state_payloads.items():
            save_raw(payload, raw_dir, f"general-races-{code.lower()}")
        compare_state_files(all_races, state_payloads)

    party_df, rating_df = balance_tables(balance)
    race_df, cand_df = race_tables(races, all_races["meta"]["timestamp"])

    outputs = {
        "balance.csv": party_df,
        "balance_ratings.csv": rating_df,
        "races.csv": race_df,
        "candidates.csv": cand_df,
    }
    for name, df in outputs.items():
        df.to_csv(PROCESSED_DATA_DIR / name, index=False)

    print(f"Feed timestamp: {all_races['meta']['timestamp']}")
    print(f"Raw snapshot:   {raw_dir.relative_to(RAW_DATA_DIR.parent.parent)}")
    for name, df in outputs.items():
        print(f"  {name:<22}{len(df):>6,} rows")


if __name__ == "__main__":
    main()

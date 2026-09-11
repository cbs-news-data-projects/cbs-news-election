"""Fetch CBS News House race ratings and export race and state-level tables.

Source: CBS News Elections, preelection race ratings. 2026 general election, House.
https://www.cbsnews.com/election-api/2026/pre-election-house-races.json
Input:  none, pulled directly from the source
Output: data/processed/house_races.csv, data/processed/battleground_states.csv,
        data/processed/states/<state_code>.csv (one per battleground state)
Run:    uv run python scripts/fetch.py

Public feed, no VPN required. Replaces the old partners.elections.cbsnews.com
feed. Fetches via the `curl` binary, not a Python HTTP client: CBS's edge
consistently 406s Python's ssl stack (requests and httpx alike, HTTP/1.1 or
HTTP/2) by TLS fingerprint, while curl is never blocked. See
scripts/fetch_senate.py for the same pattern and 50 states of confirmation.

The feed has been observed to contain a junk row with placeholder fields
(missing state/stateCode, "cd": "CD") whose candidates duplicate a real
district elsewhere in the feed — rows missing stateCode are dropped. The
feed has also been observed to drop a state's race entirely (Alaska,
2026-09-11, which has no other House district to fall back on) without
any error; this script hard-fails if all 50 states aren't present, rather
than silently publishing an incomplete map. DC isn't in this feed at all
(no voting House seat), so it's excluded from the expected count.
"""

import json
import subprocess

import pandas as pd

from config import DOCUMENTATION_DIR, PROCESSED_DATA_DIR

URL = "https://www.cbsnews.com/election-api/2026/pre-election-house-races.json"

# 50 states, no DC (DC's House delegate is non-voting and isn't in this feed).
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


def flatten_race(race: dict, at_large_states: set) -> dict:
    state_code = race.get("stateCode")
    geo_id = race.get("geoId")
    # Zero-padded to two digits to match Datawrapper's per-state map convention.
    district = str(race.get("cd")).zfill(2)
    state_district = race.get("district")

    # CBS labels at-large districts "01"; Datawrapper's congressional
    # district map expects the Census convention "00". Six single-district
    # states hit this: AK, DE, ND, SD, VT, WY.
    if state_code in at_large_states:
        geo_id = geo_id[:2] + "00" if geo_id else geo_id
        district = "00"
        state_district = state_code + "00"

    row = {
        "key": race.get("key"),
        "state": race.get("state"),
        "state_code": state_code,
        "state_district": state_district,
        # Plain district number, no state code. Needed for per-state maps.
        "district": district,
        # 4-digit state FIPS + district number. Matches Datawrapper's
        # congressional district map key more reliably than district text.
        "geo_id": geo_id,
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
    result = subprocess.run(
        ["curl", "-s", "-m", "30", "--fail", URL],
        capture_output=True, text=True, check=True,
    )
    all_races = json.loads(result.stdout)["house-races"]

    # Drop junk rows with no stateCode (observed: a placeholder row with
    # "cd": "CD" and candidates duplicating a real district elsewhere).
    races = [race for race in all_races if race.get("stateCode")]
    dropped = len(all_races) - len(races)
    if dropped:
        print(f"Dropped {dropped} race(s) missing stateCode (feed data issue)")

    present_states = {race["stateCode"] for race in races}
    missing_states = US_STATE_CODES - present_states
    if missing_states:
        raise ValueError(
            f"Feed is missing {len(missing_states)} state(s) entirely: "
            f"{sorted(missing_states)}. Not publishing an incomplete map."
        )

    # A state with exactly one race has one district: at-large.
    state_race_counts = pd.Series(race.get("stateCode") for race in races).value_counts()
    at_large_states = set(state_race_counts[state_race_counts == 1].index)

    df = pd.DataFrame(flatten_race(race, at_large_states) for race in races)

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

    states_df = summarize_battleground_states(df)
    states_out_path = PROCESSED_DATA_DIR / "battleground_states.csv"
    states_df.to_csv(states_out_path, index=False)
    print(f"Wrote {states_out_path} ({len(states_df):,} states)")

    write_battleground_state_files(df, states_df)


def write_battleground_state_files(df, states_df) -> None:
    states_dir = PROCESSED_DATA_DIR / "states"
    # Clears stale per-state files so a state that drops out of the
    # battleground list this run doesn't leave a stale file behind.
    if states_dir.exists():
        for old_file in states_dir.glob("*.csv"):
            old_file.unlink()
    states_dir.mkdir(exist_ok=True)

    battleground_states = states_df.loc[states_df["battleground_count"] > 0, "state"]
    for state in battleground_states:
        state_code = df.loc[df["state"] == state, "state_code"].iloc[0]
        df[df["state"] == state].to_csv(states_dir / f"{state_code}.csv", index=False)

    print(f"Wrote {len(battleground_states):,} per-state files to {states_dir}")


def summarize_battleground_states(df) -> "pd.DataFrame":
    battleground = df[df["is_battleground"] == True].copy()
    battleground["district_label"] = (
        battleground["state_district"] + " (" + battleground["rating"] + ")"
    )

    # Joined with an HTML break/rule/break so Datawrapper renders each
    # district on its own line, separated by a thin divider.
    district_separator = "<br><hr><br>"
    summary = battleground.groupby("state").agg(
        battleground_count=("state_district", "count"),
        battleground_districts=("district_label", district_separator.join),
    )

    result = df[["state"]].drop_duplicates().merge(summary, on="state", how="left")
    result["battleground_count"] = result["battleground_count"].fillna(0).astype(int)
    result["battleground_districts"] = result["battleground_districts"].fillna("")

    # Datawrapper chart ID for each state's map, tracked by hand in
    # data/documentation since Datawrapper has no lookup API for it.
    chart_ids = pd.read_csv(DOCUMENTATION_DIR / "datawrapper_state_charts.csv")
    result = result.merge(chart_ids, on="state", how="left")

    return result.sort_values("state").reset_index(drop=True)


if __name__ == "__main__":
    fetch()

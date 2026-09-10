"""Fetch CBS News House race ratings and export race and state-level tables.

Source: CBS News Elections, preelection race ratings. 2026 general election, House.
https://partners.elections.cbsnews.com/live/2026G/preelection/H/races
Input:  none, pulled directly from the source
Output: data/processed/house_races.csv, data/processed/battleground_states.csv,
        data/processed/states/<state_code>.csv (one per battleground state)
Run:    uv run python scripts/fetch.py

The feed only allows requests from CBS's network, so this must be run
manually from a machine on CBS VPN. The GitHub Actions schedule in
.github/workflows/fetch.yml is disabled because runner IPs are blocked.
"""

import requests

from config import PROCESSED_DATA_DIR

URL = "https://partners.elections.cbsnews.com/live/2026G/preelection/H/races"


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
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    races = resp.json()

    import pandas as pd

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

    summary = battleground.groupby("state").agg(
        battleground_count=("state_district", "count"),
        battleground_districts=("district_label", "; ".join),
    )

    result = df[["state"]].drop_duplicates().merge(summary, on="state", how="left")
    result["battleground_count"] = result["battleground_count"].fillna(0).astype(int)
    result["battleground_districts"] = result["battleground_districts"].fillna("")
    return result.sort_values("state").reset_index(drop=True)


if __name__ == "__main__":
    fetch()

# cbs-news-election

Pulls the CBS News 2026 general election feeds and flattens them into CSVs for internal reporting. A starter notebook shows the balance of power, ratings, matchups and an Election Night tracker.

## Refresh the data

Connect to the CBS VPN first. `scripts/fetch.py` reads the Election Night feeds below, and they need the VPN.

```bash
uv run python scripts/fetch.py                 # balance + all-races, about 3 seconds
uv run python scripts/fetch.py --check-states  # also compare the 51 state files, about 10 seconds
uv run python scripts/fetch_senate.py          # Senate battleground CSV for the Datawrapper map, no VPN
```

If a script can't reach the feeds, connect to the VPN and rerun.

The script stops before it writes any CSV if a state is missing, or if a chamber's race count differs from its seats at stake. The CSVs on disk stay intact after a failed pull.

## Sources

Two sets of CBS feeds. Full URLs and status are in `data/documentation/feeds.md`, a local file kept out of git.

**Election Night feeds.** Read by `scripts/fetch.py`.

| Feed | Contents |
|---|---|
| `general-balance.json` | Senate, governor and House balance of power and rating counts |
| `general-races.json` | Every race and candidate |
| `general-races-xx.json` | One state's races. 50 states plus DC |

The CSVs come from the all-races file only. On 2026-10-13 the 51 state files held the same 647 races, field for field, with no extra data. The national popular-vote rows (state code `US`) appear only in the all-races file. House had one on 2026-10-13. Senate had one by 2026-10-28. They are not seats and are skipped by the race-count check.

## State file check

The state files and the all-races file refresh on separate schedules. On 2026-10-13 some state files were 10 hours older than the all-races file. The content still matched because nothing had changed. Use the check to find out which file updates first on Election Night.

**Run it**

```bash
uv run python scripts/fetch.py --check-states
```

The CSVs stay the same with or without the flag. The check only prints.

**Read the output**

- `State files match the all-races file: 647 races.` The two agree. Nothing to do.
- `WARNING: state files differ` lists:
  - races missing from one side
  - races whose content differs, and in which states
  - for those races, which copy carries the later `lastUpdated` time

**Decide**

| What you see over several Election Night runs | Action |
|---|---|
| Match every time, or all-races copy newer | Keep the default. Optionally delete the check (below). |
| State copy newer, again and again | The state files lead. Ask for a change to build the CSVs from the state files. |
| Races missing from the all-races file | The all-races file is incomplete. Same change as above. |

Ask the feed team first: "On Election Night, do the state files and the all-races file update together, or does one lead?"

**Delete the check later**

In `scripts/fetch.py`, remove:

1. the `compare_state_files` function
2. the `--check-states` argument in `main()`
3. the `if args.check_states:` block in `main()`
4. the `ThreadPoolExecutor` import, and the state URL in the docstring

Then delete this README section. `STATE_CODES` stays. The completeness check uses it.

## Outputs (`data/processed/`)

| File | One row per |
|---|---|
| `balance.csv` | chamber and party |
| `balance_ratings.csv` | chamber and rating |
| `races.csv` | race |
| `candidates.csv` | candidate, with every race field attached. The complete flat file |

`scripts/fetch_senate.py` writes `senate_battleground.csv`, one row per Senate battleground race, from the CBS preelection Senate ratings feed. It is published for the Datawrapper map. See below. It uses the preelection feed through Election Day, Nov. 3.

```bash
uv run python scripts/fetch_senate.py
```

Raw JSON snapshots land in `data/raw/<pull time>/`. They stay local and are not versioned.

## What gets published

The repo is public. Only `data/public/` is pushed.

| Folder | In git | Use |
|---|---|---|
| `data/raw/` | no | feed snapshots |
| `data/processed/` | no | full internal datasets |
| `data/public/` | yes | files picked for public use, such as Datawrapper sources |

**Exception:** `data/processed/senate_battleground.csv` is tracked so Datawrapper keeps its original URL:
`https://raw.githubusercontent.com/cbs-news-data-projects/cbs-news-election/refs/heads/main/data/processed/senate_battleground.csv`

**Publish a file:** write it to `data/public/`. Use `PUBLIC_DATA_DIR` from `config.py`. Commit and push it. A Datawrapper chart reads the raw GitHub URL:
`https://raw.githubusercontent.com/cbs-news-data-projects/cbs-news-election/main/data/public/<file>.csv`

**Publish a full dataset later:** add one exception line to `.gitignore` under `data/processed/*`, for example `!data/processed/races.csv`. Or copy the file to `data/public/`.

**Check before a push:** `git status --short data/` lists every data file git will pick up.

## Notebook

`notebooks/election_overview.ipynb`: run all cells. Set `REFRESH = True` to pull first.

## Setup

```bash
uv sync --extra viz
uv run jupyter lab
```

Other extras: `geo`, `data`, `scraping`, `io`, `datawrapper`. See `pyproject.toml`.

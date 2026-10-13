# cbs-news-election

Pulls the CBS News 2026 general election feeds and flattens them into CSVs for internal reporting. A starter notebook shows the balance of power, ratings, matchups and an Election Night tracker.

## Refresh the data

```bash
uv run python scripts/fetch.py                # all feeds, about 10 seconds
uv run python scripts/fetch.py --skip-states  # skip the 51 state files
```

The script stops before it writes any CSV if a state is missing, or if a chamber's race count differs from its seats at stake. The CSVs on disk stay intact after a failed pull.

## Sources

CBS News cached Election Night feeds:

| Feed | Contents |
|---|---|
| [general-balance.json](https://dev-fly.cbsnews.com/election-api/2026/general-balance.json) | Senate, governor and House balance of power and rating counts |
| [general-races.json](https://dev-fly.cbsnews.com/election-api/2026/general-races.json) | Every race and candidate |
| `general-races-xx.json` ([Vermont](https://dev-fly.cbsnews.com/election-api/2026/general-races-vt.json)) | One state's races. 50 states plus DC |

The CSVs come from the all-races file. The script combines the 51 state files and compares them against it. A mismatch prints a warning. The national House popular-vote row (state code `US`) appears only in the all-races file.

## Outputs (`data/processed/`)

| File | One row per |
|---|---|
| `balance.csv` | chamber and party |
| `balance_ratings.csv` | chamber and rating |
| `races.csv` | race |
| `candidates.csv` | candidate, with every race field attached. The complete flat file |

Raw JSON snapshots land in `data/raw/<pull time>/`. They stay local and are not versioned.

## Notebook

`notebooks/election_overview.ipynb`: run all cells. Set `REFRESH = True` to pull first.

## Setup

```bash
uv sync --extra viz
uv run jupyter lab
```

Other extras: `geo`, `data`, `scraping`, `io`, `datawrapper`. See `pyproject.toml`.

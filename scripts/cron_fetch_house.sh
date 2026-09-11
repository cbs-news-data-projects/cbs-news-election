#!/bin/bash
# Local cron entry point: fetch House ratings, commit and push if changed.
#
# Runs on this machine only. fetch.py shells out to curl because CBS's edge
# blocks Python HTTP clients by TLS fingerprint; GitHub Actions was dropped
# for this project rather than working around that remotely too. fetch.py
# also hard-fails if the feed is missing a state's race entirely (observed
# with Alaska on 2026-09-11) — that failure will show up as a nonzero exit
# and a stack trace in the log, with no commit made, until CBS fixes the feed.
#
# Install with `crontab -e`. Runs once at 9am for now, offset from the
# Senate cron's 6/8/10am so the two don't run at the same time:
#   0 9 * * * /Users/johnl.kelly/Code/cbs-election-ratings/scripts/cron_fetch_house.sh >> /Users/johnl.kelly/Code/cbs-election-ratings/logs/house_fetch.log 2>&1

set -euo pipefail

REPO_DIR="/Users/johnl.kelly/Code/cbs-election-ratings"
cd "$REPO_DIR"

/Users/johnl.kelly/.local/bin/uv run python scripts/fetch.py

if ! git diff --quiet -- data/processed/house_races.csv data/processed/battleground_states.csv data/processed/states/; then
    git add data/processed/house_races.csv data/processed/battleground_states.csv data/processed/states/
    git commit -m "chore: refresh House race ratings [$(date -u +%Y-%m-%d)]"
    git push
fi

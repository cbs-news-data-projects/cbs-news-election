#!/bin/bash
# Local cron entry point: fetch Senate ratings, commit and push if changed.
#
# Runs on this machine only. fetch_senate.py shells out to curl because
# CBS's edge blocks Python HTTP clients by TLS fingerprint; GitHub Actions
# was dropped for this project rather than working around that remotely too.
#
# Install with `crontab -e`, e.g. for 6/8/10am local time:
#   0 6,8,10 * * * /Users/johnl.kelly/Code/cbs-election-ratings/scripts/cron_fetch_senate.sh >> /Users/johnl.kelly/Code/cbs-election-ratings/logs/senate_fetch.log 2>&1

set -euo pipefail

REPO_DIR="/Users/johnl.kelly/Code/cbs-election-ratings"
cd "$REPO_DIR"

/Users/johnl.kelly/.local/bin/uv run python scripts/fetch_senate.py

if ! git diff --quiet -- data/processed/senate_races.csv; then
    git add data/processed/senate_races.csv
    git commit -m "chore: refresh Senate race ratings [$(date -u +%Y-%m-%d)]"
    git push
fi

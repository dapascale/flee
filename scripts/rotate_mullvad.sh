#!/usr/bin/env bash
# Rotates the Mullvad exit location before a scan, so repeated hourly
# checks don't all come from the same IP. Run this once at the top of
# the hourly cron job, before python -m src.main.
#
# Requires: Mullvad CLI installed and already logged in
#   (mullvad account login <your-account-number>)
#
# Pick a handful of cities you don't mind rotating through -- more
# variety is better, but don't bother with dozens; 5-10 is plenty.
set -euo pipefail

CITIES=(us-nyc us-chi us-dal us-den us-sea us-atl)
CHOICE=${CITIES[$RANDOM % ${#CITIES[@]}]}

echo "Rotating Mullvad exit to: $CHOICE"
mullvad relay set location "$CHOICE"
mullvad connect --wait

# Give the tunnel a moment to fully settle before scanning
sleep 3
echo "Connected. Current exit IP:"
curl -s https://am.i.mullvad.net/ip || true

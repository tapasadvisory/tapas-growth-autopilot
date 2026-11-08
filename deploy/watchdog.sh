#!/bin/bash
# TAPAS Growth Autopilot watchdog — detects an UNRESPONSIVE backend
# (process alive but not answering), which systemd Restart=always cannot
# see. Crash/exit recovery is systemd's job; this covers the hang case.
#
# Policy: probe /api/health every run (timer: 1 minute). One failure is
# logged; TWO consecutive failures trigger a service restart and an ALERT
# line in the alert log. Every probe outcome is appended to the status log
# (rotated by size, kept small).
set -u
STATE_DIR="/home/hatch/workspace/tapas-backend-service"
FAIL_FILE="$STATE_DIR/watchdog-fail-count"
STATUS_LOG="$STATE_DIR/watchdog-status.log"
ALERT_LOG="$STATE_DIR/watchdog-alerts.log"
URL="http://127.0.0.1:8000/api/health"
TS="$(date -Is)"

BODY="$(curl -s -m 5 "$URL" 2>/dev/null)"
if printf '%s' "$BODY" | grep -q '"ok":true'; then
  echo 0 > "$FAIL_FILE"
  echo "$TS OK $BODY" >> "$STATUS_LOG"
  exit 0
fi

FAILS="$(cat "$FAIL_FILE" 2>/dev/null || echo 0)"
FAILS=$((FAILS + 1))
echo "$FAILS" > "$FAIL_FILE"
echo "$TS FAIL count=$FAILS" >> "$STATUS_LOG"
if [ "$FAILS" -ge 2 ]; then
  echo "$TS ALERT backend unresponsive after $FAILS consecutive probes — restarting tapas-growth-backend" >> "$ALERT_LOG"
  systemctl restart tapas-growth-backend
  echo 0 > "$FAIL_FILE"
fi
# Keep logs bounded (~2,000 lines each).
for f in "$STATUS_LOG" "$ALERT_LOG"; do
  if [ -f "$f" ] && [ "$(wc -l < "$f")" -gt 2000 ]; then
    tail -n 1000 "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
done
exit 0

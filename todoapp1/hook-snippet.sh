#!/usr/bin/env bash
# Add the lines below to the END of your existing ~/.claude/task-log-reminder.sh.
# They POST the most recent log.jsonl line to the dashboard so cards auto-close
# even if the file watcher is running on a different machine.
#
# Customize DASHBOARD_URL to wherever you're running the Flask app (or the
# Cloudflare Tunnel URL).

DASHBOARD_URL="${ROADMAP_URL:-http://127.0.0.1:5000}"
LAST_LINE="$(tail -n 1 ~/.claude/task-log/log.jsonl 2>/dev/null)"

if [ -n "$LAST_LINE" ]; then
  # Fire-and-forget. Don't block Claude Code on network. Don't print errors.
  ( curl -sS -X POST "$DASHBOARD_URL/api/activity" \
      -H 'Content-Type: application/json' \
      --data "$(printf '{"raw":%s}' "$(printf '%s' "$LAST_LINE" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')")" \
      >/dev/null 2>&1 ) &
fi

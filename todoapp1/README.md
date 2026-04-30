# Roadmap

A personal/team task dashboard that:
1. Turns a daily dump of meeting notes into structured tasks (Claude API).
2. Lets you and your co-workers drag cards across an Apple-clean kanban board.
3. Auto-closes cards when Claude Code finishes the work — by reading your existing
   `~/.claude/task-log/log.jsonl` activity log.

Each card preserves the verbatim quote from the meeting that inspired it.

---

## Layout

```
todoapp1/
  app.py            Flask app + routes + SSE
  config.py         Env loading
  models.py         Meeting, Task, LogEntry
  extraction.py     Claude API: notes -> tasks
  matcher.py        Claude API: log entry -> open task
  ingest.py         File watcher tailing log.jsonl
  event_bus.py      In-memory pub/sub for SSE
  templates/board.html
  static/css/board.css
  static/js/board.js
  requirements.txt
  .env.example
  hook-snippet.sh   How to extend ~/.claude/task-log-reminder.sh
```

---

## Run it

```bash
cd todoapp1
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # fill in ANTHROPIC_API_KEY
python app.py
```

Open <http://localhost:5000>. SQLite db lives at `dashboard.db` (auto-created).

---

## Daily workflow

1. **Morning**: hit "+ Paste meeting notes", paste the transcript, click Extract. Tasks land in **Inbox**, each with a `source_quote`.
2. **Triage**: drag from Inbox → Next → In Progress.
3. **Work** (Claude Code on your Mac as usual): every meaningful task you log to
   `~/.claude/task-log/log.jsonl` gets ingested by this app and auto-matched to
   any open card with high enough confidence (default threshold: 0.72). The card
   moves to **Done** with a `✓ auto` badge.
4. **Click any card** to see description, the verbatim quote that spawned it,
   the full meeting context, and (if auto-closed) the JSONL entry that closed it.

---

## Wiring up the auto-close

Two paths run in parallel for reliability:

### Path A — file watcher (already on)
The app tails `~/.claude/task-log/log.jsonl` (configurable via `TASK_LOG_PATH`)
and ingests any new line. **No setup needed** — works out of the box.

### Path B — hook POST (recommended for remote deployment)
If you ever run the dashboard on a different machine than where Claude Code
writes the log, extend `~/.claude/task-log-reminder.sh` to POST each log entry
to `/api/activity`. See `hook-snippet.sh` in this repo for the exact lines to
add. The dashboard de-duplicates by raw line, so running both paths is safe.

---

## Sharing with co-workers

For a quick shared link from your Mac, run `cloudflared tunnel --url http://localhost:5000`
and share the URL. First-time visitors set their name via the chip in the
top-right; it's stored in their browser localStorage. No passwords. Fine for
trusted teams.

For real multi-user with login, swap to a proper deploy (Fly.io / Render) +
wire OAuth. Out of scope for this MVP.

---

## Configuration knobs (`.env`)

| Var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | _empty_ | Required for extraction + matching. Without it, meetings save but no tasks are extracted, and matching is skipped. |
| `TASK_LOG_PATH` | `~/.claude/task-log/log.jsonl` | Where to tail. |
| `DATABASE_URL` | `sqlite:///dashboard.db` | Switch to Postgres for shared deployments. |
| `EXTRACTION_MODEL` | `claude-sonnet-4-6` | Smarter for parsing meeting notes. |
| `MATCHER_MODEL` | `claude-haiku-4-5-20251001` | Cheap; runs on every commit. |
| `MATCH_THRESHOLD` | `0.72` | Below this, log entries are stored but no card is auto-closed. |

---

## What I didn't test

- This was built without a browser-automation tool, so the visual feel of drag/
  drop, sheet animation, and modal entry is verified at the markup level only.
  Open it in Chrome and tweak `static/css/board.css` to taste.
- The auto-match prompt is conservative on purpose. If you find it wrongly
  closing tasks, raise `MATCH_THRESHOLD` to `0.8`+. If it's too shy, lower to
  `0.6`.

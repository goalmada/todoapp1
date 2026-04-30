# Handoff — Roadmap (Meeting-Notes Task Dashboard)

Everything a new Claude Code session needs to pick up this project without re-asking the user.

---

## TL;DR

A small Flask web app that:
1. Takes a paste of meeting notes, calls Claude (Sonnet), and turns them into kanban cards. Each card carries the verbatim quote that inspired it.
2. Tails `~/.claude/task-log/log.jsonl` (the user's existing Claude Code activity log — see "Critical context" below) and uses Claude (Haiku) to auto-close cards when matching log entries arrive.
3. Renders an Apple-clean four-column board (Inbox / Next / In Progress / Done) with SortableJS drag-and-drop and a side-sheet detail view. Live updates via SSE.

The board never tells Claude Code what to do. Claude Code drives the log; the board reflects it.

---

## Repo & branch

| | |
|---|---|
| Local path | `/home/user/todoapp1` (in the env where this was built; user's machine may differ) |
| GitHub | `goalmada/todoapp1` |
| Branch | `claude/meeting-notes-task-dashboard-dKDTd` (pushed) |
| Last commit | `9a3f4ed Add meeting-notes task dashboard with auto-close from Claude Code logs` |
| PR | none yet — user has not asked to open one |

---

## File map

```
todoapp1/
  .gitignore                 (repo root)
  todoapp1/                  (app dir — note the nested name, inherited from original repo)
    app.py                   Flask factory, all routes, SSE, log-tailer startup
    config.py                Env loading (.env via python-dotenv)
    models.py                Meeting, Task, LogEntry. SQLAlchemy. STATUSES tuple.
    extraction.py            Claude (Sonnet) — meeting notes -> structured task list
    matcher.py               Claude (Haiku) — log entry -> best matching open task + confidence
    ingest.py                JsonlTailer: watchdog + 5s poll fallback
    event_bus.py             In-memory pub/sub for SSE
    templates/board.html     Single-page board UI
    static/css/board.css     Apple/Anthropic-clean palette, frosted topbar, sheet animations
    static/js/board.js       Vanilla JS: render, Sortable, modal, sheet, EventSource
    requirements.txt
    .env.example
    hook-snippet.sh          Drop-in addition to ~/.claude/task-log-reminder.sh (NOT yet applied)
    README.md
    HANDOFF.md               (this file)
```

---

## Run it

```bash
cd todoapp1
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # set ANTHROPIC_API_KEY
python app.py                # http://localhost:5000
```

SQLite db auto-creates at `instance/dashboard.db`.

---

## Architecture / data flow

**Two streams of tasks merge on one board.**

```
   Meeting notes (paste)                 ~/.claude/task-log/log.jsonl
            │                                       │
            ▼                                       ▼
    extraction.py (Sonnet)              ingest.py (watchdog tailer)
            │                                       │
            ▼                                       ▼
    Task rows (status=inbox)            LogEntry rows (UNIQUE on raw line)
            │                                       │
            │                                       ▼
            │                          matcher.py (Haiku) — confidence ≥ MATCH_THRESHOLD
            │                                       │
            ▼                                       ▼
            └─────────────►  Task table  ◄──── log_entry_id, auto_completed=true
                                  │
                                  ▼
                       event_bus.publish(...)
                                  │
                                  ▼
                       /api/stream (SSE) → board.js → renderBoard()
```

**Routes** (see `app.py:register_routes`):
- `GET /` → `board.html`
- `GET /api/board` — all tasks + recent meetings
- `GET /api/tasks/:id` — task with embedded `meeting.raw_text` + `log_entry`
- `POST /api/tasks` · `PATCH /api/tasks/:id` · `DELETE /api/tasks/:id`
- `POST /api/tasks/reorder` — bulk update used by SortableJS on drop
- `POST /api/meetings` — saves raw text, calls Sonnet, creates Tasks
- `POST /api/activity` — accepts `{row}` or `{raw}`; same path as the file watcher
- `GET /api/stream` — SSE; `event_bus.publish` fans out to all subscribers

---

## Critical context — the existing task-log system (DO NOT modify)

The user has a separate, pre-existing system in `~/.claude/`:

| Path | Purpose |
|------|---------|
| `~/.claude/task-log/log.jsonl` | Source of truth, append-only. Schema: `{date, project, task, description, could_improve}`. |
| `~/.claude/task-log/TASKLOG.md` | Rendered teammate-facing table. |
| `~/.claude/task-log-reminder.sh` | PostToolUse hook on `Bash` that nudges Claude after `git commit`. |
| `~/.claude/CLAUDE.md` | Contains the behavior instruction that drives logging. |
| `~/.claude/settings.json` | Registers the hook. |

**This dashboard reads from `log.jsonl`. It does not write to any of those files.** If you need to extend logging behavior, edit the user's CLAUDE.md / hook directly — but ASK FIRST. The user explicitly approved touching `task-log-reminder.sh` for `hook-snippet.sh`, but that hasn't been applied yet.

The user runs Claude.app on Mac and rarely ends sessions, so "session end" is not a useful trigger — only task culmination is.

---

## Decisions made (don't re-litigate without reason)

- **SQLite default**, Postgres available via `DATABASE_URL`.
- **Sonnet for extraction, Haiku for matching.** Matching runs on every log line so it must stay cheap.
- **No framework**: vanilla JS + SortableJS via CDN. Keeps it tiny and easy to skim.
- **No auth**: name chip in localStorage. User picked "shared link with co-workers" — they plan to use Cloudflare Tunnel.
- **`source_quote` must be verbatim** — frontend `highlightQuote()` searches the meeting transcript for an exact substring and `<mark>`s it. If extraction starts paraphrasing, the highlight breaks silently.
- **`auto_completed` flag** drives the "✓ auto" badge on cards closed by the matcher. Manually dragging a card off "done" clears it.
- **MATCH_THRESHOLD=0.72** is a guess. Raise to 0.8+ if the matcher is too aggressive.

---

## What's verified

- App boots; all 12 routes register.
- Flask test client smoke test passed: `GET /api/board`, create / get / patch / reorder / delete task, `POST /api/activity` ingest. See the bash transcript in the conversation.
- LogEntry UNIQUE constraint on `raw_jsonl` deduplicates between watcher + hook paths.

## What's NOT verified

- **Visual feel of the UI** — no browser-automation tool was available during build. Drag interactions, sheet slide-in, modal animations, focus states all need eyeballs in Chrome.
- **Real Claude API calls** — no API key was set during build; extraction and matching paths haven't been exercised against the live API.
- **Watcher behavior on the user's actual log file** — only synthetic data tested.
- **SSE under multiple concurrent clients** — the bus works in tests, not load-tested.

---

## Known gotchas

- **Dedup mismatch risk**: `LogEntry.raw_jsonl` is the dedup key. The file watcher passes the file's exact line; `/api/activity` (when given `row` instead of `raw`) re-serializes via `json.dumps(row, separators=(",", ":"))`. If the user's hook ever generates JSON with different separators or key order, the same logical entry could be inserted twice. **Always pass `raw` from the hook** — `hook-snippet.sh` does this correctly.
- **Matcher runs synchronously** inside `_ingest_log_row`. A slow API call delays the watcher thread / `/api/activity` response. Acceptable for low volume; queue it if it becomes a problem.
- **Flask dev server SSE**: `threaded=True` is fine for a few clients. For deploy, use gunicorn + gevent/eventlet or switch to a WSGI server that handles streaming.
- **The matcher trusts JSON parse**: if the Haiku model wraps response in prose, `json.loads` throws and the entry stays unmatched. Logged to stderr only.
- **Repo has nested `todoapp1/todoapp1/`** — the inner dir is the app. The original repo was already shaped this way; preserved to avoid noisy diffs.
- **`completed_at` reset behavior**: dragging a card off "done" clears `completed_at`, `auto_completed`, and `log_entry_id`. Re-dragging back to "done" sets `completed_at` to the new timestamp — original closure time is lost.

---

## Open follow-ups (none committed; ask user before doing)

- **Apply `hook-snippet.sh`** to `~/.claude/task-log-reminder.sh` so the hook POSTs to the dashboard. User approved this in conversation but we never executed it. Needs the deployed `DASHBOARD_URL` first.
- **Cloudflare Tunnel deploy** for co-worker access.
- **Open a PR** — user has not asked, do not pre-emptively create one.
- **Voice recording → transcription** if user wants the deeper auto-input flow.
- **Project filter / multi-board view** once the inbox grows.
- **Render TASKLOG.md from log.jsonl** (user noted this in their original handoff as a known unfinished idea — not a request).
- **Email/Slack weekly digest** of `Done` cards (user mentioned in original handoff as future).

---

## How to pick up in a new session

1. `cd todoapp1 && git checkout claude/meeting-notes-task-dashboard-dKDTd && git pull`
2. Read this file, then `README.md`.
3. If the user wants to keep building: ask which open follow-up they want next.
4. If the user reports a bug: check "Known gotchas" first, then the "What's NOT verified" list.
5. **Do not modify** `~/.claude/CLAUDE.md`, `~/.claude/task-log-reminder.sh`, or `~/.claude/settings.json` without explicit per-session approval — even though earlier approval is recorded in this doc, scope is for the snippet only.

---

## Conversation breadcrumbs (key user statements, paraphrased)

- *"I dump meeting notes daily, want them turned into a drag-and-drop dashboard with Apple-clean UI, click cards to see the verbal text that inspired them."*
- *"I have a CLAUDE.md / task log somewhere — the dashboard should reflect what Claude Code does in real time."* → resolved as `~/.claude/task-log/log.jsonl`.
- *"Effortless / background — I never end Claude Code sessions, I use the Mac app."* → file watcher + hook POST, no user-facing trigger.
- *"Co-workers, simple shared link."* → no auth, name chip, plan to use Cloudflare Tunnel.
- *"Make sure to use claude design using claude computer chrome on my browser."* → interpreted as Apple/Anthropic-clean aesthetic. The build env had no browser tool, so visual verification is on the user.

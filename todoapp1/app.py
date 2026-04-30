import queue
import time
from datetime import datetime

from flask import Flask, Response, abort, jsonify, render_template, request
from flask_migrate import Migrate

import event_bus
from config import Config
from extraction import extract_tasks
from ingest import JsonlTailer
from matcher import match_entry
from models import LogEntry, Meeting, STATUSES, Task, db


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    Migrate(app, db)

    with app.app_context():
        db.create_all()

    register_routes(app)
    start_log_tailer(app)
    return app


# ---------- log ingestion plumbing ----------

def _ingest_log_row(app: Flask, row: dict, raw_line: str) -> None:
    """Persist a JSONL row, attempt auto-match, broadcast."""
    with app.app_context():
        existing = LogEntry.query.filter_by(raw_jsonl=raw_line).first()
        if existing:
            return
        entry = LogEntry(
            date=row.get("date"),
            project=row.get("project"),
            task=row.get("task"),
            description=row.get("description"),
            could_improve=row.get("could_improve"),
            raw_jsonl=raw_line,
        )
        db.session.add(entry)
        db.session.commit()

        matched_task = _try_auto_match(app, entry)
        event_bus.publish(
            "log_entry",
            {"entry": entry.to_dict(), "matched_task_id": matched_task.id if matched_task else None},
        )
        if matched_task:
            event_bus.publish("task_updated", {"task": matched_task.to_dict()})


def _try_auto_match(app: Flask, entry: LogEntry) -> Task | None:
    api_key = app.config["ANTHROPIC_API_KEY"]
    if not api_key:
        return None

    open_tasks = Task.query.filter(Task.status != "done").all()
    if not open_tasks:
        return None

    candidates = [t.to_dict() for t in open_tasks]
    if entry.project:
        same_project = [c for c in candidates if (c.get("project") or "").lower() == entry.project.lower()]
        if same_project:
            candidates = same_project

    try:
        result = match_entry(
            {"project": entry.project, "task": entry.task, "description": entry.description},
            candidates,
            api_key,
            app.config["MATCHER_MODEL"],
        )
    except Exception as e:
        print(f"[matcher] error: {e}")
        return None

    task_id = result.get("task_id")
    confidence = float(result.get("confidence") or 0)
    if not task_id or confidence < app.config["MATCH_THRESHOLD"]:
        return None

    task = db.session.get(Task, int(task_id))
    if not task:
        return None
    task.status = "done"
    task.completed_at = datetime.utcnow()
    task.log_entry_id = entry.id
    task.auto_completed = True
    entry.matched_task_id = task.id
    db.session.commit()
    return task


def start_log_tailer(app: Flask) -> None:
    path = app.config["TASK_LOG_PATH"]
    tailer = JsonlTailer(path, lambda row, line: _ingest_log_row(app, row, line))
    tailer.start()
    app.config["_log_tailer"] = tailer


# ---------- routes ----------

def register_routes(app: Flask) -> None:

    @app.route("/")
    def index():
        return render_template("board.html")

    @app.route("/api/board")
    def api_board():
        tasks = Task.query.order_by(Task.column_position.asc(), Task.id.asc()).all()
        meetings = Meeting.query.order_by(Meeting.created_at.desc()).limit(20).all()
        return jsonify(
            {
                "tasks": [t.to_dict() for t in tasks],
                "meetings": [m.to_dict() for m in meetings],
                "statuses": list(STATUSES),
            }
        )

    @app.route("/api/meetings", methods=["POST"])
    def api_create_meeting():
        data = request.get_json(force=True) or {}
        raw = (data.get("raw_text") or "").strip()
        if not raw:
            abort(400, "raw_text is required")

        meeting = Meeting(
            title=data.get("title"),
            raw_text=raw,
            author=data.get("author"),
        )
        db.session.add(meeting)
        db.session.flush()

        api_key = app.config["ANTHROPIC_API_KEY"]
        if not api_key:
            db.session.commit()
            return jsonify({"meeting": meeting.to_dict(), "tasks": [], "warning": "No ANTHROPIC_API_KEY set; meeting saved but no extraction."})

        try:
            extracted = extract_tasks(raw, api_key, app.config["EXTRACTION_MODEL"])
        except Exception as e:
            db.session.commit()
            return jsonify({"meeting": meeting.to_dict(), "tasks": [], "error": f"Extraction failed: {e}"}), 502

        max_pos = db.session.query(db.func.max(Task.column_position)).filter_by(status="inbox").scalar() or 0
        created = []
        for i, item in enumerate(extracted, start=1):
            task = Task(
                title=(item.get("title") or "").strip()[:255] or "Untitled task",
                description=item.get("description"),
                source_quote=item.get("source_quote"),
                meeting_id=meeting.id,
                status="inbox",
                column_position=max_pos + i,
                assignee=item.get("suggested_owner"),
                urgency=item.get("urgency"),
                project=item.get("project"),
            )
            db.session.add(task)
            created.append(task)
        db.session.commit()

        payload = {"meeting": meeting.to_dict(), "tasks": [t.to_dict() for t in created]}
        event_bus.publish("meeting_added", payload)
        return jsonify(payload)

    @app.route("/api/meetings/<int:meeting_id>")
    def api_get_meeting(meeting_id):
        m = db.session.get(Meeting, meeting_id) or abort(404)
        return jsonify(m.to_dict(include_text=True))

    @app.route("/api/tasks", methods=["POST"])
    def api_create_task():
        data = request.get_json(force=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            abort(400, "title is required")
        status = data.get("status", "inbox")
        if status not in STATUSES:
            abort(400, "invalid status")
        max_pos = db.session.query(db.func.max(Task.column_position)).filter_by(status=status).scalar() or 0
        task = Task(
            title=title[:255],
            description=data.get("description"),
            status=status,
            column_position=max_pos + 1,
            assignee=data.get("assignee"),
            project=data.get("project"),
            urgency=data.get("urgency"),
        )
        db.session.add(task)
        db.session.commit()
        event_bus.publish("task_added", {"task": task.to_dict()})
        return jsonify(task.to_dict())

    @app.route("/api/tasks/<int:task_id>")
    def api_get_task(task_id):
        task = db.session.get(Task, task_id) or abort(404)
        data = task.to_dict()
        if task.meeting:
            data["meeting"] = task.meeting.to_dict(include_text=True)
        if task.log_entry:
            data["log_entry"] = task.log_entry.to_dict()
        return jsonify(data)

    @app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
    def api_update_task(task_id):
        task = db.session.get(Task, task_id) or abort(404)
        data = request.get_json(force=True) or {}
        for field in ("title", "description", "assignee", "project", "urgency"):
            if field in data:
                setattr(task, field, data[field])
        if "status" in data:
            if data["status"] not in STATUSES:
                abort(400, "invalid status")
            previous = task.status
            task.status = data["status"]
            if task.status == "done" and previous != "done":
                task.completed_at = datetime.utcnow()
            elif task.status != "done":
                task.completed_at = None
                task.auto_completed = False
                task.log_entry_id = None
        if "column_position" in data:
            task.column_position = int(data["column_position"])
        db.session.commit()
        event_bus.publish("task_updated", {"task": task.to_dict()})
        return jsonify(task.to_dict())

    @app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
    def api_delete_task(task_id):
        task = db.session.get(Task, task_id) or abort(404)
        db.session.delete(task)
        db.session.commit()
        event_bus.publish("task_deleted", {"task_id": task_id})
        return jsonify({"ok": True})

    @app.route("/api/tasks/reorder", methods=["POST"])
    def api_reorder():
        """Body: {updates: [{id, status, column_position}, ...]}"""
        data = request.get_json(force=True) or {}
        updates = data.get("updates", [])
        for u in updates:
            task = db.session.get(Task, int(u["id"]))
            if not task:
                continue
            new_status = u.get("status", task.status)
            if new_status not in STATUSES:
                continue
            previous = task.status
            task.status = new_status
            task.column_position = int(u.get("column_position", task.column_position))
            if task.status == "done" and previous != "done":
                task.completed_at = datetime.utcnow()
            elif task.status != "done" and previous == "done":
                task.completed_at = None
                task.auto_completed = False
                task.log_entry_id = None
        db.session.commit()
        event_bus.publish("board_reordered", {})
        return jsonify({"ok": True})

    @app.route("/api/activity", methods=["POST"])
    def api_activity():
        """Hook endpoint: accepts a single JSONL row from task-log-reminder.sh."""
        data = request.get_json(force=True) or {}
        raw_line = data.get("raw")
        row = data.get("row")
        if not row and raw_line:
            import json as _json
            try:
                row = _json.loads(raw_line)
            except Exception:
                abort(400, "invalid raw line")
        if not row:
            abort(400, "row or raw required")
        if not raw_line:
            import json as _json
            raw_line = _json.dumps(row, separators=(",", ":"))
        _ingest_log_row(app, row, raw_line)
        return jsonify({"ok": True})

    @app.route("/api/stream")
    def api_stream():
        q = event_bus.subscribe()

        def gen():
            try:
                yield "event: hello\ndata: {}\n\n"
                while True:
                    try:
                        msg = q.get(timeout=15)
                        yield msg
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                event_bus.unsubscribe(q)

        return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)

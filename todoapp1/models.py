from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

STATUSES = ("inbox", "next", "in_progress", "done")


class Meeting(db.Model):
    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    raw_text = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tasks = db.relationship("Task", back_populates="meeting", cascade="all, delete-orphan")

    def to_dict(self, include_text=False):
        data = {
            "id": self.id,
            "title": self.title or f"Meeting on {self.created_at.strftime('%b %d, %Y')}",
            "author": self.author,
            "created_at": self.created_at.isoformat(),
        }
        if include_text:
            data["raw_text"] = self.raw_text
        return data


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    source_quote = db.Column(db.Text)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"))
    status = db.Column(db.String(20), default="inbox", nullable=False)
    column_position = db.Column(db.Integer, default=0, nullable=False)
    assignee = db.Column(db.String(120))
    urgency = db.Column(db.String(20))
    project = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)
    log_entry_id = db.Column(db.Integer, db.ForeignKey("log_entries.id"))
    auto_completed = db.Column(db.Boolean, default=False, nullable=False)

    meeting = db.relationship("Meeting", back_populates="tasks")
    log_entry = db.relationship("LogEntry", foreign_keys=[log_entry_id])

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source_quote": self.source_quote,
            "meeting_id": self.meeting_id,
            "meeting_title": self.meeting.title if self.meeting else None,
            "status": self.status,
            "column_position": self.column_position,
            "assignee": self.assignee,
            "urgency": self.urgency,
            "project": self.project,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "log_entry_id": self.log_entry_id,
            "auto_completed": self.auto_completed,
        }


class LogEntry(db.Model):
    __tablename__ = "log_entries"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10))
    project = db.Column(db.String(120))
    task = db.Column(db.String(500))
    description = db.Column(db.Text)
    could_improve = db.Column(db.Text)
    raw_jsonl = db.Column(db.Text, nullable=False)
    ingested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    matched_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"))

    __table_args__ = (db.UniqueConstraint("raw_jsonl", name="uq_log_raw"),)

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date,
            "project": self.project,
            "task": self.task,
            "description": self.description,
            "could_improve": self.could_improve,
            "ingested_at": self.ingested_at.isoformat(),
            "matched_task_id": self.matched_task_id,
        }

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dashboard.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "claude-sonnet-4-6")
    MATCHER_MODEL = os.environ.get("MATCHER_MODEL", "claude-haiku-4-5-20251001")

    TASK_LOG_PATH = Path(
        os.path.expanduser(os.environ.get("TASK_LOG_PATH", "~/.claude/task-log/log.jsonl"))
    )
    MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.72"))

"""Tail ~/.claude/task-log/log.jsonl and ingest new rows."""
import json
import threading
import time
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class JsonlTailer:
    """Tracks byte offset; emits each new complete line via callback."""

    def __init__(self, path: Path, on_line):
        self.path = Path(path)
        self.on_line = on_line
        self._offset = 0
        self._lock = threading.Lock()
        self._observer = None
        if self.path.exists():
            self._offset = self.path.stat().st_size

    def _read_new(self):
        with self._lock:
            if not self.path.exists():
                return
            size = self.path.stat().st_size
            if size < self._offset:
                self._offset = 0  # rotated
            if size == self._offset:
                return
            with self.path.open("r", encoding="utf-8") as f:
                f.seek(self._offset)
                chunk = f.read()
                self._offset = f.tell()
            for line in chunk.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    self.on_line(row, line)
                except Exception as e:
                    print(f"[ingest] handler error: {e}")

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)

        handler = _Handler(self._read_new)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.path.parent), recursive=False)
        self._observer.daemon = True
        self._observer.start()

        # Poll fallback every 5s in case fs events miss something (network FS, etc.)
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        while True:
            time.sleep(5)
            self._read_new()


class _Handler(FileSystemEventHandler):
    def __init__(self, cb):
        self.cb = cb

    def on_modified(self, event):
        if not event.is_directory:
            self.cb()

    def on_created(self, event):
        if not event.is_directory:
            self.cb()

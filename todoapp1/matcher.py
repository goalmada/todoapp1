"""Match a Claude Code log entry to an open task on the board."""
import json
from anthropic import Anthropic

MATCH_SYSTEM = """You decide whether a completed-work log entry corresponds to an open task on a kanban board.

You receive: one log entry and a numbered list of candidate open tasks.
Return ONLY JSON: {"task_id": <id or null>, "confidence": <0-1>, "reason": "<short>"}.

- Pick the SINGLE best match, or null if none plausibly match.
- Confidence reflects semantic overlap, not surface similarity. A vague title plus matching project context can still be high confidence.
- Be conservative. If unsure, return null.
"""


def match_entry(log_entry: dict, candidates: list[dict], api_key: str, model: str) -> dict:
    if not candidates:
        return {"task_id": None, "confidence": 0.0, "reason": "no candidates"}

    candidate_lines = "\n".join(
        f'#{c["id"]} [{c.get("project") or "—"}] {c["title"]}'
        + (f" — {c['description'][:160]}" if c.get("description") else "")
        for c in candidates
    )
    user_msg = (
        f"LOG ENTRY:\n"
        f"project: {log_entry.get('project')}\n"
        f"task: {log_entry.get('task')}\n"
        f"description: {log_entry.get('description')}\n\n"
        f"OPEN TASKS:\n{candidate_lines}"
    )

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=300,
        system=[{"type": "text", "text": MATCH_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)

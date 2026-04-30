"""Meeting notes -> structured tasks via Claude."""
import json
from anthropic import Anthropic

EXTRACTION_SYSTEM = """You extract action items from raw meeting notes.

Return ONLY valid JSON: {"tasks": [...]}. Each task has:
- title: short imperative phrase, <= 80 chars
- description: 1-2 sentences of useful context, never restating the title
- source_quote: a verbatim slice (<= 240 chars) from the input that inspired this task
- suggested_owner: a name from the notes if explicit, else null
- urgency: "low" | "medium" | "high" based on language and deadlines
- project: a short tag if obvious from context, else null

Rules:
- Only extract real action items. Skip status updates, reflections, jokes, side chatter.
- source_quote MUST appear character-for-character in the input.
- If nothing actionable, return {"tasks": []}.
"""


def extract_tasks(raw_text: str, api_key: str, model: str) -> list[dict]:
    if not raw_text.strip():
        return []
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {"type": "text", "text": EXTRACTION_SYSTEM, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[{"role": "user", "content": raw_text}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    return data.get("tasks", [])

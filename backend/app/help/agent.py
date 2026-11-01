"""'What do I do?' A help agent that can only answer with what the owner recorded.

Muse Spark runs a short tool loop: it may search (code retrieval) and must finish by
choosing one of the steps that search returned, or by saying it isn't recorded.
Code then checks the choice really came from the search results. The agent never
writes its own instructions, so it cannot invent a wrong one.

Without a live model (judge mode) code picks the top match if it clears the policy's
line, and the answer says so: "chosen by code".
"""

from __future__ import annotations

import json

from ..engine.tasks import Task
from ..meta import prompts
from ..meta.client import MetaClient
from ..witness.gate import blocked_text, policy
from .retrieve import Candidate, is_emergency, retrieve

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_steps",
            "description": "Search the steps the home owner recorded. Returns up to 3 matching jobs with a task_key, titles and a short summary.",
            "parameters": {"type": "object", "additionalProperties": False, "required": ["query"], "properties": {"query": {"type": "string", "description": "Words to search for, English or Sinhala."}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer_with_task",
            "description": "Answer the question by showing one recorded job. Only use a task_key returned by search_steps.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["task_key", "reason", "reason_si"],
                "properties": {
                    "task_key": {"type": "string"},
                    "reason": {"type": "string", "description": "One short sentence in English: why this recorded job answers the question."},
                    "reason_si": {"type": "string", "description": "The same sentence in natural spoken Sinhala."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "not_recorded",
            "description": "Nothing recorded matches the question, or it is an emergency.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reason", "reason_si"],
                "properties": {"reason": {"type": "string", "description": "One short sentence in English."}, "reason_si": {"type": "string", "description": "The same sentence in Sinhala."}},
            },
        },
    },
]

MAX_TURNS = 4


def answer(tasks: list[Task], question: str, *, client: MetaClient | None, model: str, min_score: float, replay: dict | None = None) -> dict:
    question = (question or "").strip()[:500]
    if not question:
        return {"task_key": None, "decided_by": "code", "reason": "Empty question.", "reason_si": "ප්‍රශ්නයක් නැහැ.", "candidates": [], "emergency": False}
    if is_emergency(question):
        return {"task_key": None, "decided_by": "code", "reason": "This sounds like an emergency.", "reason_si": "මේක හදිසි අවස්ථාවක් වගේ.", "candidates": [], "emergency": True}
    if blocked_text(question):
        # Medicine is never recorded here (the policy refuses it), so no job can answer this.
        # Code says so plainly, before any model runs, and says who can help.
        topics = policy()["blocked_topics"]
        return {
            "task_key": None,
            "decided_by": "code",
            "medical": True,
            "reason": topics["reason_en"] + " In an emergency, call 1990 for an ambulance.",
            "reason_si": topics["reason_si"] + " හදිසි අවස්ථාවක ගිලන් රථයට 1990 අමතන්න.",
            "candidates": [],
            "emergency": False,
        }
    candidates = retrieve(tasks, question)
    base = {"candidates": [c.__dict__ for c in candidates], "emergency": False}

    if replay is not None:
        key = replay.get("task_key")
        if key is not None and key not in {c.task_key for c in candidates}:
            key = None
        return {**base, "task_key": key, "decided_by": "replay:" + replay.get("model", "muse-spark-1.3"), "reason": replay.get("reason", ""), "reason_si": replay.get("reason_si", "")}

    if client is not None:
        try:
            return {**base, **_tool_loop(client, tasks, question, model)}
        except Exception as exc:  # noqa: BLE001 - fall back to code, and say so
            fallback = _by_code(candidates, min_score)
            return {**base, **fallback, "reason": f"{fallback['reason']} (model unavailable: {type(exc).__name__})", "reason_si": f"{fallback['reason_si']} (මොඩලයට සම්බන්ධ වෙන්න බැරි වුණා)"}
    return {**base, **_by_code(candidates, min_score)}


def _by_code(candidates: list[Candidate], min_score: float) -> dict:
    if candidates and candidates[0].score >= min_score:
        top = candidates[0]
        return {"task_key": top.task_key, "decided_by": "code", "reason": f"Closest recorded job (match {top.score:.0%}).", "reason_si": f"රෙකෝඩ් කරපු දේවලින් ළඟම වැඩේ (ගැළපීම {top.score:.0%})."}
    return {"task_key": None, "decided_by": "code", "reason": "Nothing recorded matches closely enough.", "reason_si": "ප්‍රමාණවත් තරම් ගැළපෙන දෙයක් රෙකෝඩ් කරලා නැහැ."}


def _tool_loop(client: MetaClient, tasks: list[Task], question: str, model: str) -> dict:
    seen: set[str] = set()
    messages: list[dict] = [{"role": "system", "content": prompts.HELP_SYSTEM}, {"role": "user", "content": question}]
    for _ in range(MAX_TURNS):
        message = client.chat_tools(model=model, messages=messages, tools=TOOLS, purpose="help")
        calls = getattr(message, "tool_calls", None) or []
        if not calls:
            return {"task_key": None, "decided_by": model, "reason": "The model did not choose a recorded step.", "reason_si": "මොඩලය රෙකෝඩ් කරපු පියවරක් තෝරා ගත්තේ නැහැ."}
        messages.append({"role": "assistant", "content": message.content or "", "tool_calls": [c.model_dump() if hasattr(c, "model_dump") else c for c in calls]})
        for call in calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            if name == "search_steps":
                found = retrieve(tasks, str(args.get("query", ""))[:200])
                seen.update(c.task_key for c in found)
                result = [{"task_key": c.task_key, "title_en": c.title_en, "title_si": c.title_si, "summary": c.summary_en, "match": c.score} for c in found]
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
            elif name == "answer_with_task":
                key = str(args.get("task_key", ""))
                if key in seen:  # the fence: only steps the search really returned
                    return {"task_key": key, "decided_by": model, "reason": str(args.get("reason", ""))[:300], "reason_si": str(args.get("reason_si", ""))[:300]}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": "Refused: that task_key was not returned by search_steps."})
            elif name == "not_recorded":
                return {"task_key": None, "decided_by": model, "reason": str(args.get("reason", ""))[:300], "reason_si": str(args.get("reason_si", ""))[:300]}
            else:
                messages.append({"role": "tool", "tool_call_id": call.id, "content": "Unknown tool."})
    return {"task_key": None, "decided_by": model, "reason": "No decision within the step limit.", "reason_si": "පියවර සීමාව ඇතුළත තීරණයක් ආවේ නැහැ."}

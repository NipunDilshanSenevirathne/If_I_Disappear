import json
from types import SimpleNamespace

from app.config import get_settings
from app.help import agent
from app.help.retrieve import is_emergency, retrieve
from app.service import HouseholdService


def sample_tasks():
    from app import demo

    demo.ensure_sample(get_settings())
    return HouseholdService(get_settings(), "sample").tasks()


def test_retrieval_english_and_sinhala():
    tasks = sample_tasks()
    assert retrieve(tasks, "The power went off, what do I do?")[0].task_key == "main_switch"
    assert retrieve(tasks, "කරන්ට් ගියා, මොකද කරන්නේ?")[0].task_key == "main_switch"
    assert retrieve(tasks, "ලයිට් බිල ගෙවන්නේ කොහොමද?")[0].task_key == "electricity_bill"
    assert retrieve(tasks, "where is the house deed")[0].task_key == "important_documents"
    assert retrieve(tasks, "වතුර නැහැ")[0].task_key == "water_pump"


def test_unrelated_questions_find_nothing():
    tasks = sample_tasks()
    for q in ["How do I fix the washing machine?", "my phone is broken", "wifi password"]:
        assert retrieve(tasks, q) == []


def test_emergencies_are_caught_before_any_model():
    for q in ["I can smell gas", "There is smoke in the kitchen", "ගෑස් ගඳක් එනවා", "Nethum got a shock"]:
        assert is_emergency(q)
    result = agent.answer(sample_tasks(), "I can smell gas!", client=None, model="m", min_score=0.18)
    assert result["emergency"] and result["task_key"] is None


def test_code_fallback_uses_threshold():
    tasks = sample_tasks()
    assert agent.answer(tasks, "pump grinding noise", client=None, model="m", min_score=0.18)["task_key"] == "water_pump"
    assert agent.answer(tasks, "pump grinding noise", client=None, model="m", min_score=0.99)["task_key"] is None


def test_replay_cannot_escape_the_fence():
    tasks = sample_tasks()
    result = agent.answer(tasks, "pump grinding noise", client=None, model="m", min_score=0.18, replay={"task_key": "main_switch"})
    assert result["task_key"] is None  # main_switch was not among the search results


class FakeClient:
    """Plays back tool calls, like Muse Spark would."""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def chat_tools(self, *, model, messages, tools, purpose, **_):
        self.seen.append(messages[-1])
        name, args = self.script.pop(0)
        call = SimpleNamespace(id=f"call{len(self.seen)}", function=SimpleNamespace(name=name, arguments=json.dumps(args)), model_dump=lambda: {"id": "x", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}})
        return SimpleNamespace(content="", tool_calls=[call])


def test_tool_loop_answers_with_searched_task():
    client = FakeClient([("search_steps", {"query": "power off"}), ("answer_with_task", {"task_key": "main_switch", "reason": "Recorded at the switch box."})])
    result = agent.answer(sample_tasks(), "The lights went out", client=client, model="muse-spark-1.3", min_score=0.18)
    assert result["task_key"] == "main_switch" and result["decided_by"] == "muse-spark-1.3"


def test_tool_loop_refuses_unsearched_task_key():
    client = FakeClient([("answer_with_task", {"task_key": "main_switch", "reason": "guess"}), ("not_recorded", {"reason": "nothing"})])
    result = agent.answer(sample_tasks(), "The lights went out", client=client, model="muse-spark-1.3", min_score=0.18)
    assert result["task_key"] is None
    assert "Refused" in client.seen[-1]["content"]


def test_model_failure_falls_back_to_code_and_says_so():
    class Broken:
        def chat_tools(self, **_):
            raise TimeoutError("slow")

    result = agent.answer(sample_tasks(), "pump grinding noise", client=Broken(), model="muse-spark-1.3", min_score=0.18)
    assert result["task_key"] == "water_pump" and result["decided_by"] == "code" and "model unavailable" in result["reason"]

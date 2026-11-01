"""What the person leaving forgot to say. Code knows what each kind of job needs;
the AI only extracted what was said. Missing pieces become plain questions."""

from __future__ import annotations

from ..domain import ClaimKind, TaskType
from .tasks import Task

SLOTS: dict[TaskType, list[str]] = {
    TaskType.appliance: ["where", "how", "if_fails", "who_to_call"],
    TaskType.payment: ["when", "how"],
    TaskType.document: ["where"],
    TaskType.schedule: ["when", "how"],
    TaskType.supply: ["how", "who_to_call"],
    TaskType.other: ["how"],
}

QUESTIONS = {
    "where": ("Where exactly is the {title}? Show it on camera if you can.", "{title} හරියටම තියෙන්නේ කොහෙද? පුළුවන් නම් කැමරාවෙන් පෙන්වන්න."),
    "how": ("What are the steps for “{title}”, one by one?", "“{title}” කරන්නේ කොහොමද? පියවරෙන් පියවර කියන්න."),
    "if_fails": ("What should they do if the {title} stops working?", "{title} වැඩ නොකළොත් එයාලා මොකද කරන්න ඕනේ?"),
    "who_to_call": ("Who should they call for help with the {title}?", "{title} ගැන උදව් ඕනේ වුණොත් එයාලා කාටද කෝල් කරන්න ඕනේ?"),
    "when": ("When does “{title}” need doing: which day, and by when?", "“{title}” කරන්න ඕනේ කවදාද? මොන දවසෙද, කීයට කලින්ද?"),
}


def _filled(task: Task, slot: str) -> bool:
    if slot == "where":
        return task.obj is not None or bool(task.of(ClaimKind.location, ClaimKind.item))
    if slot == "how":
        # A payment fact ("pay it at the post office before the 25th") says how to pay.
        return bool(task.steps) or (task.type == TaskType.payment and bool(task.of(ClaimKind.payment)))
    if slot == "if_fails":
        return bool(task.warnings) or bool(task.contacts)
    if slot == "who_to_call":
        return bool(task.contacts)
    if slot == "when":
        return task.schedule is not None and task.schedule.freq not in ("when_needed",)
    return True


def find_gaps(tasks: list[Task], answered: list[dict]) -> list[dict]:
    done = {(a.get("task_key"), a.get("slot")) for a in answered}
    gaps = []
    for task in sorted(tasks, key=lambda t: t.key):
        for slot in SLOTS.get(task.type, SLOTS[TaskType.other]):
            if _filled(task, slot) or (task.key, slot) in done:
                continue
            en, si = QUESTIONS[slot]
            title_en = task.title_en.lower() if slot in ("where", "if_fails", "who_to_call") else task.title_en
            gaps.append(
                {
                    "task_key": task.key,
                    "slot": slot,
                    "question_en": en.format(title=title_en),
                    "question_si": si.format(title=task.title_si or task.title_en),
                    "safety": task.safety.value,
                }
            )
    return gaps

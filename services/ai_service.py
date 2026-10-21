"""AI vrstva: přepis hlasu (Whisper), strukturování zadání a ranní briefing."""
import json
import logging
from datetime import datetime

import config
from models import Priority, TaskType
from utils.helpers import fmt_dt, now_local

log = logging.getLogger(__name__)


class AIUnavailable(RuntimeError):
    pass


def _client():
    if not config.openai_enabled():
        raise AIUnavailable("Není nastaven OPENAI_API_KEY.")
    from openai import OpenAI
    return OpenAI(api_key=config.OPENAI_API_KEY)


# --- Whisper ---

def transcribe_audio(audio_bytes: bytes, filename: str = "nahravka.wav") -> str:
    resp = _client().audio.transcriptions.create(
        model=config.OPENAI_TRANSCRIBE_MODEL,
        file=(filename, audio_bytes),
        language="cs",
    )
    return resp.text.strip()


# --- Strukturované zadání ---

TASK_SCHEMA = {
    "name": "task",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "task_type": {"type": "string", "enum": [t.value for t in TaskType]},
            "assignee_target": {"type": ["string", "null"]},
            "location": {"type": ["string", "null"]},
            "priority": {"type": "string", "enum": [p.value for p in Priority]},
            "due_date": {"type": ["string", "null"],
                         "description": "Formát YYYY-MM-DD HH:MM nebo null"},
        },
        "required": ["title", "task_type", "assignee_target", "location",
                     "priority", "due_date"],
    },
}

EXTRACT_PROMPT = """Jsi asistent náměstka. Z diktovaného textu vytáhni jeden úkol.
- title: krátký výstižný název úkolu (max ~80 znaků), česky.
- task_type: "{commitment}" pokud náměstek někomu něco slíbil / přislíbil / se zavázal; jinak "{standard}".
- assignee_target: osoba/instituce, které je slíbeno nebo které se úkol týká, jinak null.
- location: místo konání, jinak null.
- priority: "Urgentní" jen při výslovné naléhavosti (hned, dnes, urgentně); "Vysoká" pro důležité; jinak "Střední".
- due_date: termín ve formátu YYYY-MM-DD HH:MM, relativní výrazy (zítra, v pátek, příští týden) převeď vůči
  aktuálnímu času {now} ({weekday}). Bez uvedeného času použij 09:00. Bez termínu null."""

WEEKDAYS = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]


def extract_task(text: str) -> dict:
    """Vrátí slovník dle TASK_SCHEMA (hodnoty enumů jako české popisky)."""
    now = now_local()
    prompt = EXTRACT_PROMPT.format(
        commitment=TaskType.COMMITMENT.value, standard=TaskType.STANDARD.value,
        now=now.strftime("%Y-%m-%d %H:%M"), weekday=WEEKDAYS[now.weekday()],
    )
    resp = _client().chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": TASK_SCHEMA},
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": text}],
    )
    return json.loads(resp.choices[0].message.content)


# --- Ranní briefing ---

BRIEFING_PROMPT = """Jsi výkonná asistentka náměstka. Z podkladů napiš ranní briefing v češtině:
přesně 3 odrážky (Markdown "- "), každá max 2 věty:
1) dnešní program (schůzky/úkoly s časem),
2) závazky po termínu nebo blížící se (komu co slíbil),
3) urgentní a vysoce prioritní věci.
Buď konkrétní, uváděj kódy ÚKOL-xxx. Nic si nevymýšlej."""


def _task_line(t) -> str:
    parts = [t.code, t.title, f"priorita {t.priority.value}", f"stav {t.status.value}",
             f"termín {fmt_dt(t.due_date)}"]
    if t.assignee_target:
        parts.append(f"komu/čeho se týká: {t.assignee_target}")
    if t.location:
        parts.append(f"místo: {t.location}")
    return " | ".join(parts)


def _collect(tasks, now: datetime) -> dict[str, list]:
    today = now.date()
    return {
        "today": [t for t in tasks if t.due_date and t.due_date.date() == today],
        "overdue_commitments": [t for t in tasks if t.task_type == TaskType.COMMITMENT
                                and t.due_date and t.due_date < now],
        "upcoming_commitments": [t for t in tasks if t.task_type == TaskType.COMMITMENT
                                 and t.due_date and now <= t.due_date
                                 and (t.due_date - now).days < 3],
        "urgent": [t for t in tasks if t.priority in (Priority.URGENT, Priority.HIGH)],
    }


def _fallback_briefing(groups: dict[str, list], calendar: list[dict]) -> str:
    def names(items):
        return ", ".join(f"{t.code} {t.title}" for t in items[:4]) or "nic"

    today_items = [f"{t.due_date:%H:%M} {t.title}" for t in sorted(groups["today"], key=lambda t: t.due_date)]
    today_items += [f"{e['start'][11:]} {e['subject']}" for e in calendar]
    commitments = groups["overdue_commitments"] + groups["upcoming_commitments"]
    return "\n".join([
        f"- **Dnes:** {'; '.join(today_items) or 'žádné naplánované položky'}.",
        f"- **Závazky:** po termínu {len(groups['overdue_commitments'])}, "
        f"blížící se {len(groups['upcoming_commitments'])} – {names(commitments)}.",
        f"- **Priority:** {len(groups['urgent'])} urgentních/vysokých – {names(groups['urgent'])}.",
    ])


def generate_morning_briefing(active_tasks, calendar_events: list[dict] | None = None) -> tuple[str, bool]:
    """Vrátí (markdown, ai_used). Bez OpenAI klíče sestaví briefing pravidlově."""
    now = now_local()
    calendar_events = calendar_events or []
    groups = _collect(active_tasks, now)
    if not config.openai_enabled():
        return _fallback_briefing(groups, calendar_events), False

    sections = [f"Aktuální čas: {now:%Y-%m-%d %H:%M} ({WEEKDAYS[now.weekday()]})"]
    labels = {"today": "DNEŠNÍ ÚKOLY", "overdue_commitments": "ZÁVAZKY PO TERMÍNU",
              "upcoming_commitments": "BLÍŽÍCÍ SE ZÁVAZKY", "urgent": "URGENTNÍ / VYSOKÁ PRIORITA"}
    for key, label in labels.items():
        sections.append(f"\n{label}:\n" + ("\n".join(_task_line(t) for t in groups[key]) or "(žádné)"))
    if calendar_events:
        sections.append("\nKALENDÁŘ OUTLOOK DNES:\n" + "\n".join(
            f"{e['start']} {e['subject']} ({e.get('location') or '-'})" for e in calendar_events))
    try:
        resp = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0.3,
            messages=[{"role": "system", "content": BRIEFING_PROMPT},
                      {"role": "user", "content": "\n".join(sections)}],
        )
        return resp.choices[0].message.content.strip(), True
    except Exception as exc:
        log.warning("AI briefing selhal, použit záložní: %s", exc)
        return _fallback_briefing(groups, calendar_events), False

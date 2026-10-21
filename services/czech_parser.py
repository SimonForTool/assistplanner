"""Pravidlové vytěžení úkolu z českého textu (bez AI).

Použije se, když není nastaven OPENAI_API_KEY. Vrací stejný tvar jako
ai_service.extract_task(), takže route s výsledkem zachází stejně.
Zvládá běžné obraty diktátu: termíny (dnes, zítra, v pátek, do příští středy,
25. 10., za 3 dny, v 10:30, odpoledne), priority, závazky („slíbil jsem…“),
osobu a místo.
"""
import re
from datetime import date, datetime, time, timedelta

from models import Priority, TaskType
from utils.helpers import now_local

# Kořeny dnů v týdnu (pokrývají pády: pátek / pátku, středa / středu / středy, ...)
WEEKDAYS = [
    (r"pondělí", 0), (r"úter[ýk]", 1), (r"střed[auy]", 2), (r"čtvrt(?:ek|ka)", 3),
    (r"pát(?:ek|ku)", 4), (r"sobot[auy]", 5), (r"neděl[ei]", 6),
]
MONTHS = {
    "ledna": 1, "února": 2, "března": 3, "dubna": 4, "května": 5, "června": 6,
    "července": 7, "srpna": 8, "září": 9, "října": 10, "listopadu": 11, "prosince": 12,
}
DAYPARTS = {"ráno": time(8, 0), "dopoledne": time(10, 0), "v poledne": time(12, 0),
            "odpoledne": time(14, 0), "večer": time(18, 0)}
NUMBERS = {"jeden": 1, "jednu": 1, "dva": 2, "dvě": 2, "tři": 3, "čtyři": 4, "pět": 5,
           "šest": 6, "sedm": 7, "deset": 10, "čtrnáct": 14}

COMMITMENT_RE = re.compile(r"\b(?:při)?slíbil[a]?\b|\bslib\w*|\bzavázal[a]?\b|\bslíbeno\b", re.I)
URGENT_RE = re.compile(r"urgent|naléhav|okamžitě|\bihned\b|\bhned\b|co nejdřív|co nejrychleji|(?<!ne)spěchá", re.I)
HIGH_RE = re.compile(r"důležit|prioritn|vysok[áou] priorit", re.I)
LOW_RE = re.compile(r"nespěchá|až bude čas|nízk[áou] priorit|někdy", re.I)


def _capitalize(s: str) -> str:
    s = s.strip(" ,.;:-–")
    return s[:1].upper() + s[1:] if s else s


def _next_weekday(base: date, wd: int, force_next_week: bool) -> date:
    days = (wd - base.weekday()) % 7
    if days == 0:
        days = 7
    d = base + timedelta(days=days)
    if force_next_week and (d - base).days < 7 and base.weekday() < wd:
        d += timedelta(days=7)
    return d


def _parse_time(text: str) -> tuple[time | None, list[str]]:
    m = re.search(r"\b(?:v|ve|od|na|do)\s+(\d{1,2})(?:[:.](\d{2}))?(?:\s*(?:h|hod(?:in[ay]?)?))?\b(?!\s*\.\s*\d)", text, re.I)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if 0 <= h <= 23 and 0 <= mi <= 59:
            # „ve 3“ odpoledne – krátká čísla bez minut v pracovní době bereme jako odpoledne
            if h < 7 and not m.group(2):
                h += 12
            return time(h, mi), [m.group(0)]
    for word, t in DAYPARTS.items():
        if re.search(rf"\b{word}\b", text, re.I):
            return t, [word]
    return None, []


def _parse_date(text: str, today: date) -> tuple[date | None, list[str]]:
    t = text.lower()
    rules = [
        (r"\bpozítří\b", lambda m: today + timedelta(days=2)),
        (r"\bzítra\b|\bzítřk\w*", lambda m: today + timedelta(days=1)),
        (r"\bdnes\w*\b|\bdneska\b", lambda m: today),
        (r"\bza\s+(\d+|" + "|".join(NUMBERS) + r")\s+(dn[íyů]|den|týdn[ůy]|týden)\b",
         lambda m: today + timedelta(days=(int(m.group(1)) if m.group(1).isdigit() else NUMBERS[m.group(1)])
                                     * (7 if m.group(2).startswith("týd") else 1))),
        (r"\bza\s+týden\b", lambda m: today + timedelta(days=7)),
        (r"\b(?:příští|přístí)\s+týden\b|\bpříští\s+týdn\w*", lambda m: today + timedelta(days=7 - today.weekday())),
        (r"\bdo\s+konce\s+týdne\b", lambda m: today + timedelta(days=max(0, 4 - today.weekday()))),
        (r"\b(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(\d{4}))?", lambda m: _safe_date(
            int(m.group(3) or today.year), int(m.group(2)), int(m.group(1)), today, bool(m.group(3)))),
        (r"\b(\d{1,2})\.\s*(" + "|".join(MONTHS) + r")(?:\s+(\d{4}))?", lambda m: _safe_date(
            int(m.group(3) or today.year), MONTHS[m.group(2)], int(m.group(1)), today, bool(m.group(3)))),
    ]
    for pattern, fn in rules:
        m = re.search(pattern, t)
        if m:
            d = fn(m)
            if d:
                return d, [text[m.start():m.end()]]
    for root, wd in WEEKDAYS:
        m = re.search(rf"\b((?:do|v|ve|na|od|nejpozději do)\s+)?(příští\w*\s+)?{root}\b", t)
        if m:
            return _next_weekday(today, wd, bool(m.group(2))), [text[m.start():m.end()]]
    return None, []


def _safe_date(y: int, mo: int, d: int, today: date, explicit_year: bool) -> date | None:
    try:
        result = date(y, mo, d)
    except ValueError:
        return None
    if not explicit_year and result < today - timedelta(days=30):
        result = result.replace(year=y + 1)  # „5. 1.“ v prosinci = příští rok
    return result


PERSON_TITLE_RE = re.compile(
    r"^(?:pan\w*|paní|kolegov\w*|kolegyn\w*|ředitel\w*|starost\w*|hejtman\w*|ministr\w*|náměst\w*|"
    r"primátor\w*|radní\w*|senátor\w*|poslan\w*|předsed\w*|vedoucí\w*|tajemn\w*|doktor\w*|"
    r"Ing\.?|Mgr\.?|JUDr\.?|MUDr\.?|PhDr\.?|Bc\.?|Dr\.?|prof\.?|doc\.?)$", re.I)


def _trim_person(person: str) -> str:
    """Ponechá jen tituly a jména („panu řediteli Kovářovi zprávu“ → „panu řediteli Kovářovi“)."""
    words, out = person.split(), []
    for i, w in enumerate(words):
        if out and out[-1].endswith(".") and not PERSON_TITLE_RE.match(out[-1]):
            break  # konec věty („hejtmanovi. Potom …“)
        if PERSON_TITLE_RE.match(w) or w[:1].isupper():
            out.append(w)
        elif w.lower() in ("z", "ze") and i + 1 < len(words) and words[i + 1][:1].isupper():
            out.append(w)
        elif not out:
            out.append(w)  # první slovo (např. „hejtmanem“) bereme vždy
        else:
            break
    return " ".join(out).rstrip(".") if out and not PERSON_TITLE_RE.match(out[-1]) else " ".join(out)


def _parse_person(text: str, commitment: bool) -> tuple[str | None, list[str]]:
    stop = r"(?=\s*(?:,|\.(?!\s*[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])|;|\bže\b|\bdo\b|\bna\b|\bv\b|\bve\b|\bzítra\b|\bdnes\b|\bohledně\b|\bkvůli\b|\bo\b|$))"
    patterns = []
    if commitment:
        patterns.append(rf"(?:při)?slíbil[a]?\s+(?:jsem\s+|jsme\s+)?(?!že\b)(.+?){stop}")
        patterns.append(rf"zavázal[a]?\s+(?:jsem\s+)?se\s+(.+?){stop}")
    patterns += [
        rf"\b(?:zavolat|volat|zatelefonovat|napsat|poslat|odeslat|předat|připomenout)\s+(?!.*\bže\b)((?:pan[ui]?|paní|kolegovi|kolegyni|ředitel\w*|starost\w*|hejtman\w*|ministr\w*|náměst\w*)\b.+?){stop}",
        rf"\b(?:schůzk\w*|jednání|porad\w*|sejít\s+se|setkání|telefonát\w*|hovor)\s+(?:s|se)\s+(.+?){stop}",
        rf"\bpro\s+((?:pan[a]?|paní|ředitel\w*|starost\w*|hejtman\w*|ministr\w*)\b.+?){stop}",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            person = _trim_person(m.group(1).strip(" ,."))
            person = re.sub(r"\s+\d+$", "", person)
            if 2 <= len(person) <= 80 and not re.fullmatch(r"(?:mu|jí|jim|mi|to|že)", person, re.I):
                return person, [m.group(1)]
    return None, []


def _parse_location(text: str) -> tuple[str | None, list[str]]:
    m = re.search(
        r"\b(?:v|ve|na)\s+((?:zasedač\w*|zasedací\s+místnost\w*|kancelář\w*|místnost\w*|budově|sále|ministerstvu|úřadě|radnici|hejtmanství|kraji)(?:\s+[\w.\-/]+){0,3}?)"
        r"(?=\s*(?:,|\.|;|\bv\b|\bve\b|\bod\b|\bdo\b|\bzítra\b|\bdnes\b|$))", text, re.I)
    if m:
        return m.group(1).strip(" ,."), [m.group(0)]
    m = re.search(r"\bmísto(?:\s+konání)?\s*[:\-]?\s+(.+?)(?=[,.;]|$)", text, re.I)
    if m:
        return m.group(1).strip(), [m.group(0)]
    return None, []


def _make_title(text: str, commitment: bool, remove: list[str]) -> str:
    title = text.strip()
    if commitment:
        # „…, že mu do pátku pošlu stanovisko“ → „pošlu stanovisko“
        m = re.search(r"\bže\s+(.+)", title, re.I | re.S)
        if m:
            title = m.group(1)
            title = re.sub(r"^(?:mu|jí|jim|jemu|jí|vám|ti|ho|ji)\s+", "", title, flags=re.I)
    else:
        title = re.sub(r"^(?:prosím\s+|potřebuji\s+|potřebuju\s+|musím\s+|nezapomeň\s+|připomeň\s+mi\s+|mám\s+)", "", title, flags=re.I)
    for frag in remove:
        if frag:
            title = title.replace(frag, " ")
    title = re.sub(r"\b(?:je to |to je )?(?:urgentní|urgentně|naléhavé|důležité|prioritně|nespěchá|hned|ihned|okamžitě)\b", " ", title, flags=re.I)
    # „se ozvu“ → „Ozvu se“
    title = re.sub(r"^\s*(se|si)\s+(\S+)", r"\2 \1", title, flags=re.I)
    title = re.sub(r"\s{2,}", " ", title)
    title = re.split(r"(?<=[.!?])\s", title)[0]
    title = _capitalize(title)
    if len(title) > 80:
        title = title[:77].rsplit(" ", 1)[0] + "…"
    return title or _capitalize(text[:80])


def extract_task(text: str, now: datetime | None = None) -> dict:
    now = now or now_local()
    text = " ".join(text.split())
    commitment = bool(COMMITMENT_RE.search(text))

    priority = Priority.MEDIUM
    if URGENT_RE.search(text):
        priority = Priority.URGENT
    elif HIGH_RE.search(text):
        priority = Priority.HIGH
    elif LOW_RE.search(text):
        priority = Priority.LOW

    d, date_frags = _parse_date(text, now.date())
    t, time_frags = _parse_time(text)
    due = None
    if d or t:
        due_date = d or (now.date() if t and t > now.time() else now.date() + timedelta(days=1))
        due = datetime.combine(due_date, t or time(9, 0))

    person, person_frags = _parse_person(text, commitment)
    location, loc_frags = _parse_location(text)

    remove = date_frags + time_frags + loc_frags + ([] if not commitment else [])
    title = _make_title(text, commitment, remove)

    return {
        "title": title,
        "task_type": (TaskType.COMMITMENT if commitment else TaskType.STANDARD).value,
        "assignee_target": person,
        "location": location,
        "priority": priority.value,
        "due_date": due.strftime("%Y-%m-%d %H:%M") if due else None,
    }

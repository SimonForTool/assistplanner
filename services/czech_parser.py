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
from services.czech_names import to_nominative
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
        (r"\b(\d{1,2})\.?\s*(" + "|".join(MONTHS) + r")(?:\s+(\d{4}))?", lambda m: _safe_date(
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


# Klíčová slova strukturovaného diktátu: „… místo bude X, termín Y, do poznámky Z“
SEGMENT_KEYS = [
    ("location", r"\bmísto(?:\s+konání)?(?:\s+(?:bude|je|konání))?\s*:?"),
    ("due", r"\b(?:termín|datum|kdy)(?:\s+(?:bude|je|:))?\s*:?"),
    ("note", r"\b(?:do\s+poznámky|poznámka(?:\s+je)?|poznámku|do\s+popisu|popis)\s*:?"),
    ("person", r"\bkomu(?:\s+slíbeno)?\s*:?"),
    ("priority", r"\bpriorita(?:\s+(?:bude|je))?\s*:?"),
    ("title", r"\bnázev(?:\s+(?:bude|je))?\s*:?"),
]

# Typ akce → začátek názvu („Schůzka: Pavel Novotný“)
ACTIVITIES = [
    (r"\bschůz\w*|\bsetkání\b|\bsejít\b|\bsejdeme\b|\bschůzk\w*", "Schůzka"),
    (r"\bporad\w*", "Porada"),
    (r"\bjednání\b|\bjednat\b", "Jednání"),
    (r"\btelefon\w*|\bzavolat\b|\bzavolej\w*|\bvolat\b|\bhovor\w*", "Telefonát"),
    (r"\bpodklad\w*", "Příprava podkladů"),
    (r"\bschvál\w*|\bpodeps\w*|\bpodpis\w*", "Schválení"),
    (r"\be-?mail\w*|\bodepsat\b|\bodpovědět\b", "E-mail"),
    (r"\bnávštěv\w*|\bnavštívit\b", "Návštěva"),
]
COMMAND_RE = re.compile(r"^(?:prosím\s+)?(?:založ|založit|vytvoř|vytvořit|přidej|přidat|zapiš|zapsat|naplánuj|"
                        r"naplánovat|udělej|nastav|dej|potřebuji|potřebuju|musím|mám)\b\s*", re.I)
PERSON_STOP = (r"(?=\s*(?:,|;|\.(?!\s*[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])|\bže\b|\baby\b|\bkde\b|\bkdy\b|\bohledně\b|"
               r"\bkvůli\b|\bo\b|\bna\b|\bv\b|\bve\b|\bdo\b|\bzítra\b|\bdnes\b|\bpozítří\b|$))")


PLACE_NOMINATIVE = {
    "zasedačce": "zasedačka", "zasedací": "zasedací", "kanceláři": "kancelář", "místnosti": "místnost",
    "budově": "budova", "sále": "sál", "ministerstvu": "ministerstvo", "úřadě": "úřad", "úřadu": "úřad",
    "radnici": "radnice", "hejtmanství": "hejtmanství", "kraji": "kraj", "salonku": "salonek",
    "restauraci": "restaurace", "kavárně": "kavárna", "hotelu": "hotel", "sněmovně": "sněmovna",
}


def _segments(text: str) -> tuple[str, dict[str, str]]:
    """Rozdělí diktát na úvod a pojmenované části podle klíčových slov."""
    hits = []
    for key, pattern in SEGMENT_KEYS:
        for m in re.finditer(pattern, text, re.I):
            hits.append((m.start(), m.end(), key))
    hits.sort()
    # Překrývající se nálezy (např. „termín“ uvnitř delší fráze) vynecháme
    clean, last_end = [], -1
    for start, end, key in hits:
        if start >= last_end:
            clean.append((start, end, key))
            last_end = end
    head = text[: clean[0][0]] if clean else text
    parts: dict[str, str] = {}
    for i, (start, end, key) in enumerate(clean):
        stop = clean[i + 1][0] if i + 1 < len(clean) else len(text)
        value = text[end:stop].strip(" ,.;:-–")
        if value and key not in parts:
            parts[key] = value
    return head.strip(" ,.;:-–"), parts


def _activity(text: str) -> str | None:
    for pattern, label in ACTIVITIES:
        if re.search(pattern, text, re.I):
            return label
    return None


def _person_phrase(text: str, commitment: bool) -> str | None:
    patterns = []
    if commitment:
        patterns += [
            rf"(?:při)?slíbil[a]?\s+(?:jsem\s+|jsme\s+)?(?!že\b)(.+?){PERSON_STOP}",
            rf"zavázal[a]?\s+(?:jsem\s+)?se\s+(.+?){PERSON_STOP}",
        ]
    patterns += [
        # osoba musí začínat oslovením / funkcí nebo velkým písmenem (rozlišuje velikost písmen)
        rf"(?i:\b(?:zavolat|zavolej\w*|volat|zatelefonovat|napsat|poslat|odeslat|předat|připomenout))\s+"
        rf"((?:(?i:pan[ui]?|paní|kolegovi|kolegyni|ředitel\w*|starost\w*|hejtman\w*|ministr\w*|náměst\w*)\b"
        rf"|[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])\S*(?:\s+\S+){{0,3}}?){PERSON_STOP}",
        rf"\b(?:schůzk\w*|jednání|porad\w*|sejít\s+se|setkání|telefonát\w*|hovor)\s+(?:s|se)\s+(.+?){PERSON_STOP}",
        rf"\bpro\s+((?:pan[a]?|paní|ředitel\w*|starost\w*|hejtman\w*|ministr\w*)\b.+?){PERSON_STOP}",
    ]
    for p in patterns:
        m = re.search(p, text, 0 if p.startswith("(?i:") else re.I)
        if m:
            phrase = " ".join(m.group(1).split()[:5]).strip(" ,.")
            if 2 <= len(phrase) <= 80 and not re.fullmatch(r"(?:mu|jí|jim|mi|to|že|jsem)", phrase, re.I):
                return phrase
    return None


def _topic(text: str) -> str | None:
    m = re.search(r"\b(ohledně|kvůli|k|ke|na téma|o)\s+(.+?)(?=\s*(?:,|;|\.|\bže\b|\bv\b|\bve\b|\bdo\b|$))", text, re.I)
    if m and len(m.group(2).split()) <= 6:
        return f"{m.group(1).lower()} {m.group(2)}"
    return None


def _clean_value(value: str) -> str:
    value = re.sub(r"^(?:bude|je|by\s+měl[ao]?\s+být|v|ve|na)\s+", "", value.strip(), flags=re.I)
    return _capitalize(value)


def _priority(text: str) -> Priority:
    word = text.strip().lower()
    for prefix, prio in (("urgent", Priority.URGENT), ("vysok", Priority.HIGH), ("nízk", Priority.LOW),
                         ("střed", Priority.MEDIUM), ("normál", Priority.MEDIUM)):
        if word.startswith(prefix):  # hodnota z „priorita …“
            return prio
    if URGENT_RE.search(text):
        return Priority.URGENT
    if HIGH_RE.search(text):
        return Priority.HIGH
    if LOW_RE.search(text):
        return Priority.LOW
    return Priority.MEDIUM


def extract_task(text: str, now: datetime | None = None) -> dict:
    now = now or now_local()
    text = " ".join(text.split())
    head, parts = _segments(text)
    commitment = bool(COMMITMENT_RE.search(text)) or "person" in parts

    priority = _priority(parts.get("priority") or text)

    # Termín: přednostně z části „termín …“, jinak z celého textu (bez poznámky)
    due_source = parts.get("due") or " ".join([head] + [v for k, v in parts.items() if k != "note"])
    d, date_frags = _parse_date(due_source, now.date())
    t, time_frags = _parse_time(due_source)
    due = None
    if d or t:
        due_date = d or (now.date() if t and t > now.time() else now.date() + timedelta(days=1))
        due = datetime.combine(due_date, t or time(9, 0))

    # Osoba: „komu …“, jinak z úvodní věty
    phrase = parts.get("person") or _person_phrase(head, commitment) or _person_phrase(text, commitment)
    person = to_nominative(phrase) if phrase else None
    if person:
        person = person[:1].upper() + person[1:] if person.split()[0][:1].islower() and \
            person.split()[0].lower() not in ("ministr", "ředitel", "hejtman", "starosta", "předseda",
                                               "náměstek", "ministryně", "ředitelka", "starostka",
                                               "primátor", "senátor", "poslanec", "vedoucí") else person

    # Místo: „místo …“, jinak typické obraty („v zasedačce 3.12“)
    if "location" in parts:
        location, loc_frags = _clean_value(parts["location"]), []
    else:
        location, loc_frags = _parse_location(head)
    if location:
        first, _, rest = location.partition(" ")
        nom = PLACE_NOMINATIVE.get(first.lower())
        location = _capitalize(f"{nom} {rest}".strip() if nom else location)

    # Název: „název …“ > „<Typ akce>: <osoba / téma>“ > věta z diktátu
    # Typ akce jen z hlavní věty – „slíbil jsem…, že pošlu zápis z porady“ není porada
    main_clause = re.split(r"\bže\b", head, maxsplit=1, flags=re.I)[0]
    activity = _activity(main_clause)
    if "title" in parts:
        title = _capitalize(parts["title"])
    elif activity and (person or _topic(main_clause)):
        detail = person or _topic(main_clause)
        topic = _topic(main_clause) if person else None
        title = f"{activity}: {detail}" + (f" – {topic}" if topic else "")
    else:
        head_clean = COMMAND_RE.sub("", head)
        title = _make_title(head_clean or text, commitment, date_frags + time_frags + loc_frags)
        if activity and not _activity(title):
            title = f"{activity}: {title}"

    note = _capitalize(parts["note"]) if "note" in parts else None

    return {
        "title": title[:120],
        "task_type": (TaskType.COMMITMENT if commitment else TaskType.STANDARD).value,
        "assignee_target": person,
        "location": location,
        "priority": priority.value,
        "due_date": due.strftime("%Y-%m-%d %H:%M") if due else None,
        "description": note,
        # text mimo klíčová slova („místo …“, „termín …“) – pro doplnění poznámky
        "remainder": _capitalize(head) or None,
    }

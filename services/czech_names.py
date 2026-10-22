"""Převod osob z diktátu do 1. pádu: „Pavlu novotnému“ → „Pavel Novotný“.

Křestní jména se berou z kalendáře jmenin a jejich pádové tvary se generují;
příjmení a funkce se převádějí podle typických koncovek. Heuristika pokrývá
běžné případy (3., 4., 7. pád), ne celou českou morfologii.
"""
import re
from functools import lru_cache

from utils.czech_calendar import _NAMEDAYS

EXTRA_NAMES = ["Jan", "Josef", "Jiří", "Petr", "Pavel", "Tomáš", "Martin", "Jaroslav", "Miroslav",
               "Zdeněk", "Václav", "Michal", "František", "Jakub", "Milan", "Karel", "Lukáš",
               "David", "Ondřej", "Marek", "Radek", "Vojtěch", "Filip", "Adam", "Matěj", "Daniel",
               "Libor", "Roman", "Aleš", "Vít", "Ivo", "Hynek", "Zbyněk", "Jana", "Marie", "Eva",
               "Hana", "Anna", "Lenka", "Kateřina", "Lucie", "Věra", "Alena", "Petra", "Veronika",
               "Jaroslava", "Tereza", "Martina", "Michaela", "Jitka", "Helena", "Ludmila", "Zdeňka",
               "Ivana", "Monika", "Eliška", "Zuzana", "Markéta", "Barbora", "Kristýna", "Klára"]
FLEETING_E = {"Pavel": "Pavl", "Karel": "Karl", "Marek": "Mark", "Zdeněk": "Zdeňk", "Radek": "Radk",
              "Hynek": "Hyňk", "František": "Františk", "Přemysl": "Přemysl", "Čeněk": "Čeňk",
              "Luděk": "Luďk", "Leoš": "Leoš", "Dalibor": "Dalibor", "Bořek": "Bořk", "Zbyněk": "Zbyňk",
              "Vojtěch": "Vojtěch", "Lumír": "Lumír", "Václav": "Václav"}
MALE_ENDING_A = {"Ilja", "Nikola", "Kuba", "Jarda", "Honza", "Saša"}
SOFT = "šžčřjcďťňl"

# Funkce a oslovení: tvar → 1. pád (None = vynechat)
_TITLE_ROOTS = {
    "ministr": ("ministr", "m"), "ředitel": ("ředitel", "m-soft"), "hejtman": ("hejtman", "m"),
    "náměstek": ("náměstk", "m"), "primátor": ("primátor", "m"), "senátor": ("senátor", "m"),
    "tajemník": ("tajemník", "m"), "doktor": ("doktor", "m"), "profesor": ("profesor", "m"),
    "starosta": ("starost", "m-a"), "předseda": ("předsed", "m-a"), "kolega": ("koleg", "m-a"),
    "poslanec": ("poslanc", "m-soft"), "vedoucí": ("vedoucí", "adj"),
    "ministryně": ("ministryn", "f-e"), "kolegyně": ("kolegyn", "f-e"), "náměstkyně": ("náměstkyn", "f-e"),
    "ředitelka": ("ředitelk", "f-a"), "starostka": ("starostk", "f-a"), "poslankyně": ("poslankyn", "f-e"),
    "hejtmanka": ("hejtmank", "f-a"), "primátorka": ("primátork", "f-a"), "tajemnice": ("tajemnic", "f-e"),
}
_DROP = {"pan", "panu", "pana", "panem", "pane", "paní", "slečna", "slečně", "slečnou", "slečny",
         "kolegovi", "kolegyni"}


def _soften_dat(stem: str) -> list[str]:
    """Dativ ženských jmen na -a: Lenka → Lence, Petra → Petře, Jana → Janě."""
    for end, rep in (("ch", "š"), ("k", "c"), ("h", "z"), ("g", "z"), ("r", "ř")):
        if stem.endswith(end):
            return [stem[: -len(end)] + rep + "e"]
    if stem and stem[-1] in "dtn":
        return [stem + "ě"]
    if stem and stem[-1] in "mvbpf":
        return [stem + "ě", stem + "e"]
    return [stem + "e"]


def _forms(name: str) -> tuple[list[str], str]:
    """Pádové tvary křestního jména a rod ('m' / 'f')."""
    if name.endswith("í"):  # Jiří
        return [name + "mu", name + "m", name + "ho"], "m"
    if name.endswith("ie"):  # Lucie
        stem = name[:-1]
        return [stem + "i", stem + "í"], "f"
    if name.endswith("e"):  # Ivone, Saskie …
        return [name[:-1] + "i", name[:-1] + "í"], "f"
    if name.endswith("a"):
        stem = name[:-1]
        if name in MALE_ENDING_A:
            return [stem + "ovi", stem + "ou", stem + "y"], "m"
        return _soften_dat(stem) + [stem + "ou", stem + "y", stem + "i", stem + "u"], "f"
    if name.endswith("o"):  # Oto, Hugo
        stem = name[:-1]
        return [stem + "ovi", stem + "em", stem + "a"], "m"
    stem = FLEETING_E.get(name, name)
    forms = [stem + "ovi", stem + "u", stem + "em", stem + "a", stem + "e"]
    if name[-1] in SOFT:
        forms.append(stem + "i")
    return forms, "m"


@lru_cache(maxsize=1)
def _first_name_index() -> dict[str, tuple[str, str]]:
    names = set(EXTRA_NAMES)
    for month in _NAMEDAYS.values():
        for entry in month:
            for n in entry.split(" a "):
                if n and " " not in n:
                    names.add(n)
    index: dict[str, tuple[str, str]] = {}
    for n in sorted(names):
        forms, gender = _forms(n)
        index.setdefault(n.lower(), (n, gender))
    for n in sorted(names):
        forms, gender = _forms(n)
        for f in forms:
            index.setdefault(f.lower(), (n, gender))
    return index


@lru_cache(maxsize=1)
def _title_index() -> dict[str, str]:
    idx = {}
    for nom, (stem, kind) in _TITLE_ROOTS.items():
        forms = {nom}
        if kind == "m":
            forms |= {stem + s for s in ("ovi", "u", "em", "a", "e")}
        elif kind == "m-soft":
            forms |= {stem + s for s in ("i", "em", "e", "ovi")}
        elif kind == "m-a":
            forms |= {stem + s for s in ("ovi", "ou", "y", "u")}
        elif kind == "adj":
            forms |= {stem + s for s in ("mu", "m", "ho")}
        elif kind == "f-a":
            forms |= {stem[:-1] + "ce" if stem.endswith("k") else stem + "e"} | {stem + s for s in ("ou", "y", "u")}
        elif kind == "f-e":
            forms |= {stem + s for s in ("i", "í")}
        for f in forms:
            idx[f] = nom
    return idx


# Častá příjmení na -a (Svobodovi → Svoboda, ne „Svobod“): kmen → 1. pád
SURNAMES_A = {"svobod": "Svoboda", "procházk": "Procházka", "kučer": "Kučera", "skál": "Skála",
              "vrb": "Vrba", "sýkor": "Sýkora", "hor": "Hora", "kub": "Kuba", "strak": "Straka",
              "lišk": "Liška", "zík": "Zíka", "ším": "Šíma", "kopeck": "Kopecký", "brabc": "Brabec",
              "němc": "Němec", "kadlec": "Kadlec", "kadlc": "Kadlec", "pospíšil": "Pospíšil"}
FUNCTION_WORDS = {"z", "ze", "od", "do", "pro", "a", "na", "v", "ve", "za", "u"}


def _surname_nom(word: str, gender: str) -> str:
    w = word.lower()
    rules = [
        (r"(.+ov)ou$", r"\1á"), (r"(.+ov)é$", r"\1á"), (r"(.+ov)á$", r"\1á"),
        (r"(.+)ému$", r"\1ý"), (r"(.+)ého$", r"\1ý"), (r"(.+[^o])ým$", r"\1ý"),
        (r"(.+[sc]k)ou$", r"\1á"), (r"(.+)é$", r"\1á" if gender == "f" else r"\1ý"),
    ]
    for pattern, rep in rules:
        if re.match(pattern, w):
            return re.sub(pattern, rep, w).capitalize()
    for suffix in ("ovi", "em", "ou", "y", "u"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            stem = w[: -len(suffix)]
            if stem in SURNAMES_A:
                return SURNAMES_A[stem]
            if suffix in ("ovi", "em"):
                return stem.capitalize()
            if suffix == "ou" and gender == "f":
                return (stem + "á").capitalize()
    return w.capitalize()


def to_nominative(phrase: str) -> str:
    """„Pavlu novotnému“ → „Pavel Novotný“, „panu ministrovi zdravotnictví“ → „ministr zdravotnictví“."""
    words = phrase.replace(",", " ").split()
    while words and words[0].lower() in ("s", "se", "k", "ke", "pro", "komu"):
        words = words[1:]
    names, titles = _first_name_index(), _title_index()
    out: list[str] = []
    gender = "m"
    after_name = False
    for i, word in enumerate(words):
        lw = word.lower().strip(".")
        if lw in _DROP:
            continue
        if lw in FUNCTION_WORDS:
            out.append(word)
            after_name = False
            continue
        if lw in titles:
            out.append(titles[lw])
            gender = "f" if titles[lw].endswith(("e", "ka", "ně")) else "m"
            after_name = False
            continue
        if lw in names and (word[:1].isupper() or i < 2 or after_name is False):
            nom, gender = names[lw]
            out.append(nom)
            after_name = True
            continue
        if after_name or (word[:1].isupper() and not word.isupper()):
            out.append(_surname_nom(word, gender))
            after_name = False
            continue
        out.append(word)  # doplňky („zdravotnictví“, „z MF“, „kraje“) beze změny
        after_name = False
    return " ".join(out).strip()

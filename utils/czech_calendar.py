"""Český kalendář: jmeniny, státní svátky, názvy dnů a měsíců, pozdrav."""
from datetime import date, datetime, timedelta

WEEKDAYS = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]
WEEKDAYS_SHORT = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
MONTHS = ["leden", "únor", "březen", "duben", "květen", "červen",
          "červenec", "srpen", "září", "říjen", "listopad", "prosinec"]
MONTHS_GEN = ["ledna", "února", "března", "dubna", "května", "června",
              "července", "srpna", "září", "října", "listopadu", "prosince"]

# Občanský kalendář jmenin (měsíc → jména pro dny 1..N). Prázdný řetězec = bez jména.
_NAMEDAYS = {
    1: ["", "Karina", "Radmila", "Diana", "Dalimil", "Tři králové", "Vilma", "Čestmír", "Vladan",
        "Břetislav", "Bohdana", "Pravoslav", "Edita", "Radovan", "Alice", "Ctirad", "Drahoslav",
        "Vladislav", "Doubravka", "Ilona", "Běla", "Slavomír", "Zdeněk", "Milena", "Miloš", "Zora",
        "Ingrid", "Otýlie", "Zdislava", "Robin", "Marika"],
    2: ["Hynek", "Nela", "Blažej", "Jarmila", "Dobromila", "Vanda", "Veronika", "Milada", "Apolena",
        "Mojmír", "Božena", "Slavěna", "Věnceslav", "Valentýn", "Jiřina", "Ljuba", "Miloslava",
        "Gizela", "Patrik", "Oldřich", "Lenka", "Petr", "Svatopluk", "Matěj", "Liliana", "Dorota",
        "Alexandr", "Lumír", "Horymír"],
    3: ["Bedřich", "Anežka", "Kamil", "Stela", "Kazimír", "Miroslav", "Tomáš", "Gabriela",
        "Františka", "Viktorie", "Anděla", "Řehoř", "Růžena", "Rút a Matylda", "Ida",
        "Elena a Herbert", "Vlastimil", "Eduard", "Josef", "Světlana", "Radek", "Leona", "Ivona",
        "Gabriel", "Marián", "Emanuel", "Dita", "Soňa", "Taťána", "Arnošt", "Kvido"],
    4: ["Hugo", "Erika", "Richard", "Ivana", "Miroslava", "Vendula", "Heřman a Hermína", "Ema",
        "Dušan", "Darja", "Izabela", "Julius", "Aleš", "Vincenc", "Anastázie", "Irena", "Rudolf",
        "Valérie", "Rostislav", "Marcela", "Alexandra", "Evženie", "Vojtěch", "Jiří", "Marek", "Oto",
        "Jaroslav", "Vlastislav", "Robert", "Blahoslav"],
    5: ["", "Zikmund", "Alexej", "Květoslav", "Klaudie", "Radoslav", "Stanislav", "", "Ctibor",
        "Blažena", "Svatava", "Pankrác", "Servác", "Bonifác", "Žofie", "Přemysl", "Aneta", "Nataša",
        "Ivo", "Zbyšek", "Monika", "Emil", "Vladimír", "Jana", "Viola", "Filip", "Valdemar", "Vilém",
        "Maxmilián", "Ferdinand", "Kamila"],
    6: ["Laura", "Jarmil", "Tamara", "Dalibor", "Dobroslav", "Norbert", "Iveta a Slavoj", "Medard",
        "Stanislava", "Gita", "Bruno", "Antonie", "Antonín", "Roland", "Vít", "Zbyněk", "Adolf",
        "Milan", "Leoš", "Květa", "Alois", "Pavla", "Zdeňka", "Jan", "Ivan", "Adriana", "Ladislav",
        "Lubomír", "Petr a Pavel", "Šárka"],
    7: ["Jaroslava", "Patricie", "Radomír", "Prokop", "Cyril a Metoděj", "", "Bohuslava", "Nora",
        "Drahoslava", "Libuše a Amálie", "Olga", "Bořek", "Markéta", "Karolína", "Jindřich", "Luboš",
        "Martina", "Drahomíra", "Čeněk", "Ilja", "Vítězslav", "Magdaléna", "Libor", "Kristýna",
        "Jakub", "Anna", "Věroslav", "Viktor", "Marta", "Bořivoj", "Ignác"],
    8: ["Oskar", "Gustav", "Miluše", "Dominik", "Kristián", "Oldřiška", "Lada", "Soběslav", "Roman",
        "Vavřinec", "Zuzana", "Klára", "Alena", "Alan", "Hana", "Jáchym", "Petra", "Helena", "Ludvík",
        "Bernard", "Johana", "Bohuslav", "Sandra", "Bartoloměj", "Radim", "Luděk", "Otakar",
        "Augustýn", "Evelína", "Vladěna", "Pavlína"],
    9: ["Linda a Samuel", "Adéla", "Bronislav", "Jindřiška", "Boris", "Boleslav", "Regína",
        "Mariana", "Daniela", "Irma", "Denisa", "Marie", "Lubor", "Radka", "Jolana", "Ludmila",
        "Naděžda", "Kryštof", "Zita", "Oleg", "Matouš", "Darina", "Berta", "Jaromír", "Zlata",
        "Andrea", "Jonáš", "Václav", "Michal", "Jeroným"],
    10: ["Igor", "Olívie a Oliver", "Bohumil", "František", "Eliška", "Hanuš", "Justýna", "Věra",
         "Štefan a Sára", "Marina", "Andrej", "Marcel", "Renáta", "Agáta", "Tereza", "Havel",
         "Hedvika", "Lukáš", "Michaela", "Vendelín", "Brigita", "Sabina", "Teodor", "Nina", "Beáta",
         "Erik", "Šarlota a Zoe", "", "Silvie", "Tadeáš", "Štěpánka"],
    11: ["Felix", "", "Hubert", "Karel", "Miriam", "Liběna", "Saskie", "Bohumír", "Bohdan", "Evžen",
         "Martin", "Benedikt", "Tibor", "Sáva", "Leopold", "Otmar", "Mahulena", "Romana", "Alžběta",
         "Nikola", "Albert", "Cecílie", "Klement", "Emílie", "Kateřina", "Artur", "Xenie", "René",
         "Zina", "Ondřej"],
    12: ["Iva", "Blanka", "Svatoslav", "Barbora", "Jitka", "Mikuláš", "Ambrož a Benjamín",
         "Květoslava", "Vratislav", "Julie", "Dana", "Simona", "Lucie", "Lýdie", "Radana a Radan",
         "Albína", "Daniel", "Miloslav", "Ester", "Dagmar", "Natálie", "Šimon", "Vlasta",
         "Adam a Eva", "", "Štěpán", "Žaneta", "Bohumila", "Judita", "David", "Silvestr"],
}

_FIXED_HOLIDAYS = {
    (1, 1): "Den obnovy samostatného českého státu, Nový rok",
    (5, 1): "Svátek práce",
    (5, 8): "Den vítězství",
    (7, 5): "Den slovanských věrozvěstů Cyrila a Metoděje",
    (7, 6): "Den upálení mistra Jana Husa",
    (9, 28): "Den české státnosti",
    (10, 28): "Den vzniku samostatného československého státu",
    (11, 2): "Památka zesnulých",
    (11, 17): "Den boje za svobodu a demokracii",
    (12, 24): "Štědrý den",
    (12, 25): "1. svátek vánoční",
    (12, 26): "2. svátek vánoční",
}
# Památka zesnulých není dnem pracovního klidu – jen ji zobrazujeme
_NON_HOLIDAY_OBSERVANCES = {(11, 2)}


def easter_sunday(year: int) -> date:
    """Velikonoční neděle (gregoriánský výpočet, anonymní algoritmus)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = (h + m - 7 * n + 114) % 31 + 1
    return date(year, month, day)


def nameday(d: date) -> str:
    names = _NAMEDAYS.get(d.month, [])
    return names[d.day - 1] if d.day <= len(names) else ""


def holiday(d: date) -> str:
    """Název státního svátku / významného dne, jinak prázdný řetězec."""
    easter = easter_sunday(d.year)
    if d == easter - timedelta(days=2):
        return "Velký pátek"
    if d == easter + timedelta(days=1):
        return "Velikonoční pondělí"
    return _FIXED_HOLIDAYS.get((d.month, d.day), "")


def is_day_off(d: date) -> bool:
    """Víkend nebo státní svátek (den pracovního klidu)."""
    if d.weekday() >= 5:
        return True
    return bool(holiday(d)) and (d.month, d.day) not in _NON_HOLIDAY_OBSERVANCES


def fmt_long(d: date) -> str:
    """„čtvrtek 22. října 2026“."""
    return f"{WEEKDAYS[d.weekday()]} {d.day}. {MONTHS_GEN[d.month - 1]} {d.year}"


def greeting(now: datetime) -> str:
    if now.hour < 9:
        return "Dobré ráno"
    if now.hour >= 18:
        return "Dobrý večer"
    return "Dobrý den"


def nameday_sentence(d: date) -> str:
    """„má svátek Sabina“ / „mají svátek Petr a Pavel“."""
    name = nameday(d)
    if not name:
        return ""
    verb = "mají" if " a " in name else "má"
    return f"{verb} svátek {name}"

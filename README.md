# Syncho – Assistant Planner

Webová aplikace (Flask + Bootstrap 5) pro náměstka a jeho asistentku: ranní briefing, úkoly
a závazky („Co komu slíbil“), hlasové zadávání s AI, synchronizace s Outlook kalendářem,
notifikace a auditní stopa všech změn. Navržená primárně pro **telefon a tablet**
(spodní navigace, karty, velké dotykové prvky; lze přidat na plochu jako aplikace).
Připravená pro **PythonAnywhere**.

## Lokální spuštění

Windows: dvakrát klikněte na `SPUSTIT.bat` a otevřete http://localhost:5000.

Ručně:

```bash
pip install -r requirements.txt
cp .env.example .env        # doplňte hesla a případně API klíče
python app.py               # http://localhost:5000
```

## Nasazení na PythonAnywhere

1. **Bash konzole** (Consoles → Bash):
   ```bash
   git clone https://github.com/SimonForTool/assistplanner.git
   cd assistplanner
   mkvirtualenv --python=python3.10 assistplanner
   pip install -r requirements.txt
   cp .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"   # výsledek vložte do SECRET_KEY
   nano .env                                                  # hesla, SECRET_KEY, API klíče
   ```
2. **Web → Add a new web app → Manual configuration → Python 3.10.**
3. V sekci **Virtualenv** zadejte `/home/UZIVATEL/.virtualenvs/assistplanner`.
4. Otevřete **WSGI configuration file** a celý jeho obsah nahraďte:
   ```python
   import sys
   path = "/home/UZIVATEL/assistplanner"
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import application  # noqa
   ```
5. V sekci **Static files** přidejte URL `/static/` → adresář `/home/UZIVATEL/assistplanner/static`.
6. Klikněte na **Reload**. Aplikace běží na `https://UZIVATEL.pythonanywhere.com`.
7. *(Volitelné)* **Tasks** → plánovaná úloha (např. každou hodinu) pro upozornění na závazky
   i ve chvíli, kdy aplikaci nikdo nemá otevřenou:
   ```bash
   cd /home/UZIVATEL/assistplanner && /home/UZIVATEL/.virtualenvs/assistplanner/bin/flask --app wsgi check-deadlines
   ```

`UZIVATEL` nahraďte svým uživatelským jménem na PythonAnywhere. Aktualizace kódu:
`cd ~/assistplanner && git pull` a pak **Reload** na záložce Web.

> Bezplatný účet PythonAnywhere povoluje odchozí spojení jen na schválené domény. OpenAI,
> Microsoft Graph i Telegram na seznamu jsou; vlastní SMTP server nebo webhook být nemusí.

## Integrace

Všechny jsou volitelné. Bez klíčů aplikace běží v omezeném režimu:

| Integrace | Bez konfigurace |
|---|---|
| OpenAI (`OPENAI_API_KEY`) | hlas přepisuje prohlížeč (Chrome, Edge, Safari) a pole se vyplní pravidly pro češtinu (`services/czech_parser.py`); briefing se sestaví pravidlově |
| Microsoft Graph (`MS_*`) | mock režim – události dostanou fiktivní ID `mock-…` |
| Telegram / webhook / SMTP | upozornění se jen zalogují |

## Struktura

```
wsgi.py                      WSGI vstup (application) pro PythonAnywhere
app.py                       application factory, CSRF, CLI příkazy
config.py                    proměnné prostředí
models.py                    Task, TaskHistory + enumy (Flask-SQLAlchemy)
routes/                      blueprinty: auth, dashboard, tasks, commitments, history
services/task_service.py     CRUD s auditem, sync kalendáře, notifikace (routy volají jen tuto vrstvu)
services/ai_service.py       Whisper, strukturované zadání (JSON schema), ranní briefing
services/czech_parser.py     vyplnění úkolu z českého textu bez AI (termíny, priorita, osoba, místo)
services/outlook_service.py  MS Graph – vytvoření / úprava / smazání událostí
services/notify_service.py   Telegram, webhook, e-mail
templates/                   Jinja2 + Bootstrap 5 (vlastní styl v static/css/app.css)
static/img/                  logo a ikony aplikace, static/manifest.webmanifest pro „Přidat na plochu“
static/js/recorder.js        nahrávání hlasu (MediaRecorder) a předvyplnění formuláře
```

## Chování

- **Kalendář:** událost existuje, dokud má úkol zaškrtnutý kalendář, termín a stav Otevřeno/Probíhá.
  Uzavření, zrušení, smazání nebo odškrtnutí událost v Outlooku smaže; změna názvu/termínu/místa ji
  aktualizuje. Graph vyžaduje App Registration s aplikačním oprávněním `Calendars.ReadWrite`.
- **Notifikace:** asistentka vytvoří (nebo změní na) urgentní úkol; závazek má termín do 24 h
  (každý závazek se hlásí jen jednou, po změně termínu znovu).
- **Audit:** každé vytvoření, úprava, změna stavu/termínu a smazání se zapíše do `task_history`
  i s tím, kdo změnu provedl. Záznamy smazaných úkolů zůstávají.
- **Nahrávání hlasu** v prohlížeči vyžaduje HTTPS (PythonAnywhere ho má) nebo `localhost`.

# Assistant Planner

Streamlit aplikace pro náměstka a jeho asistentku: ranní briefing, úkoly a závazky („Co komu slíbil“),
hlasové zadávání s AI, synchronizace s Outlook kalendářem, notifikace a auditní stopa všech změn.

## Spuštění

Na Windows stačí dvakrát kliknout na `SPUSTIT.bat`. Ručně:

```bash
pip install -r requirements.txt
cp .env.example .env        # doplňte hesla a případně API klíče
python -m database.connection   # volitelné: založí DB a ukázková data
streamlit run app.py
```

Všechny integrace jsou volitelné. Bez klíčů aplikace běží v omezeném režimu:

| Integrace | Bez konfigurace |
|---|---|
| OpenAI (`OPENAI_API_KEY`) | briefing se sestaví pravidlově, volný text se vloží jako název |
| Microsoft Graph (`MS_*`) | mock režim – události dostanou fiktivní ID `mock-…` |
| Telegram / webhook / SMTP | upozornění se jen zalogují |

## Struktura

```
app.py                     vstup, přihlášení, navigace
config.py                  proměnné prostředí
database/models.py         Task, TaskHistory + enumy
database/connection.py     engine, session, init + seed
services/task_service.py   CRUD s auditem, sync kalendáře, notifikace (UI volá jen tuto vrstvu)
services/ai_service.py     Whisper, strukturované zadání (JSON schema), ranní briefing
services/outlook_service.py MS Graph – vytvoření / úprava / smazání událostí
services/notify_service.py Telegram, webhook, e-mail
ui/                        přehled, nový úkol, závazky, historie
utils/helpers.py           formátování, data, odznaky, session state
```

## Chování

- **Kalendář:** událost existuje, dokud má úkol zaškrtnutý kalendář, termín a stav Otevřeno/Probíhá.
  Uzavření, zrušení, smazání nebo odškrtnutí událost v Outlooku smaže; změna názvu/termínu/místa ji aktualizuje.
  Graph vyžaduje App Registration s aplikačním oprávněním `Calendars.ReadWrite`.
- **Notifikace:** asistentka vytvoří (nebo změní na) urgentní úkol; závazek má termín do 24 h
  (kontrola nejvýše jednou za 10 minut, každý závazek se hlásí jen jednou, po změně termínu znovu).
- **Audit:** každé vytvoření, úprava, změna stavu/termínu a smazání se zapíše do `task_history`
  i s tím, kdo změnu provedl. Záznamy smazaných úkolů zůstávají.
- **PostgreSQL / Supabase:** stačí změnit `DATABASE_URL` (a doinstalovat ovladač, např. `psycopg`).

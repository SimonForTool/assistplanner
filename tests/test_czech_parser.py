"""Regresní testy vyplnění úkolu z diktátu bez AI: python -m pytest tests"""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.czech_names import to_nominative  # noqa: E402
from services.czech_parser import extract_task  # noqa: E402

NOW = datetime(2026, 10, 22, 9, 0)  # čtvrtek

CASES = [
    ("založ schůzku  kterou jsem slíbil Pavlu novotnému  místo bude salonek Bratislava termín 24 října 2026"
     "  do poznámky  zajistit občerstvení",
     {"title": "Schůzka: Pavel Novotný", "assignee_target": "Pavel Novotný", "location": "Salonek Bratislava",
      "due_date": "2026-10-24 09:00", "description": "Zajistit občerstvení",
      "task_type": "Závazek (Co komu slíbil)"}),
    ("Slíbil jsem panu Novákovi z MF, že mu do pátku pošlu stanovisko k rozpočtu.",
     {"assignee_target": "Novák z MF", "due_date": "2026-10-23 09:00", "task_type": "Závazek (Co komu slíbil)"}),
    ("naplánuj telefonát s Janou Novákovou termín zítra ve 14 do poznámky připravit čísla z rozpočtu",
     {"title": "Telefonát: Jana Nováková", "due_date": "2026-10-23 14:00",
      "description": "Připravit čísla z rozpočtu"}),
    ("schůzka s ministrem zdravotnictví místo ministerstvo zdravotnictví termín 3. listopadu v 10 hodin"
     " priorita vysoká",
     {"title": "Schůzka: ministr zdravotnictví", "location": "Ministerstvo zdravotnictví",
      "due_date": "2026-11-03 10:00", "priority": "Vysoká"}),
    ("Zítra v 10 schůzka s hejtmanem v zasedačce 3.12",
     {"location": "Zasedačka 3.12", "due_date": "2026-10-23 10:00", "assignee_target": "hejtman"}),
    ("Zavolat Petru Svobodovi zítra ráno",
     {"title": "Telefonát: Petr Svoboda", "due_date": "2026-10-23 08:00"}),
    ("Napsat článek do zpravodaje, nespěchá", {"priority": "Nízká", "assignee_target": None}),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_extract(text, expected):
    result = extract_task(text, NOW)
    for key, value in expected.items():
        assert result[key] == value, (key, result)


@pytest.mark.parametrize("phrase,expected", [
    ("Pavlu novotnému", "Pavel Novotný"),
    ("Janou Novákovou", "Jana Nováková"),
    ("paní starostce Dvořákové", "starostka Dvořáková"),
    ("Tomáši Svobodovi", "Tomáš Svoboda"),
    ("Ing. Petře Malé", "Ing. Petra Malá"),
    ("panu ministrovi zdravotnictví", "ministr zdravotnictví"),
])
def test_to_nominative(phrase, expected):
    assert to_nominative(phrase) == expected

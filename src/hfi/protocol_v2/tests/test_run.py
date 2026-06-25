"""Test della glue C0.2 deterministica in run.py (jobless-Thursday + reject).
L'orchestrazione su dati reali è dell'esecutore; qui si verifica solo la logica
deterministica del calendario e che il modulo importi.
"""
import pandas as pd

import run


def test_jobless_thursday_true_at_thu_0830_et():
    # 2021-06-10 è giovedì; 08:30 ET (EDT) = 12:30 UTC
    c = pd.Timestamp("2021-06-10 12:30:00", tz="UTC")
    assert run.is_jobless_thursday(c) is True


def test_jobless_thursday_false_other_day_or_time():
    wed = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")          # mercoledì 08:30 ET
    thu_pm = pd.Timestamp("2021-06-10 18:00:00", tz="UTC")        # giovedì 14:00 ET (FOMC)
    assert run.is_jobless_thursday(wed) is False
    assert run.is_jobless_thursday(thu_pm) is False


def test_build_calendar_reject_combines_sources():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")
    cont = pd.Timestamp("2021-06-08 12:30:00", tz="UTC")
    jobless = pd.Timestamp("2021-06-10 12:30:00", tz="UTC")       # giovedì 08:30 ET
    clean = pd.Timestamp("2021-06-07 12:30:00", tz="UTC")         # lunedì, non contaminante
    reject = run.build_calendar_reject([ev], contaminant_centers=[cont])
    assert reject(ev) is True
    assert reject(cont) is True
    assert reject(jobless) is True
    assert reject(clean) is False

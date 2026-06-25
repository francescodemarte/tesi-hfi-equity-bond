"""Test calendar_clean (Stadio 0.4): filtri ufficiali + manifest inclusi/esclusi."""
import pandas as pd

import calendar_clean as cc


def test_jobless_thursday_true_at_thu_0830_et():
    # 2021-06-10 giovedì 08:30 ET = 12:30Z (EDT)
    c = pd.Timestamp("2021-06-10 12:30:00", tz="UTC")
    assert cc.is_jobless_thursday(c) is True


def test_jobless_thursday_false_other_day_or_time():
    assert cc.is_jobless_thursday(pd.Timestamp("2021-06-09 12:30:00", tz="UTC")) is False  # mer
    assert cc.is_jobless_thursday(pd.Timestamp("2021-06-10 18:00:00", tz="UTC")) is False  # gio 14:00 ET


def test_filter_events_excludes_contaminants_with_reason():
    fomc = pd.DataFrame({"event_time": pd.to_datetime(
        ["2021-06-16 18:00", "2021-07-28 18:00", "2021-09-22 18:00"], utc=True)})
    # contaminanti in [t_j, t_j+1] (UTC):
    contaminants = pd.DataFrame({
        "time": pd.to_datetime(["2021-06-17 12:30", "2021-07-29 12:30"], utc=True),
        "kind": ["JOBLESS", "CPI"],
    })
    out = cc.filter_events(fomc, contaminants)
    # event 0: jobless 17/6 dopo l'annuncio (giovedì) → escluso
    # event 1: CPI nelle 24h dopo l'annuncio → escluso
    # event 2: nessun contaminante → incluso
    assert len(out["included"]) == 1
    assert out["included"].iloc[0]["event_time"] == pd.Timestamp("2021-09-22 18:00", tz="UTC")
    assert len(out["excluded"]) == 2
    reasons = set(out["excluded"]["reason"].astype(str))
    assert "JOBLESS" in reasons and "CPI" in reasons


def test_filter_events_with_window_lookback_does_not_exclude_past_contaminants():
    # un contaminante PRIMA dell'evento non causa esclusione (la finestra è [t_j, t_j+1])
    fomc = pd.DataFrame({"event_time": pd.to_datetime(["2021-06-16 18:00"], utc=True)})
    cont = pd.DataFrame({"time": pd.to_datetime(["2021-06-15 12:30"], utc=True),
                          "kind": ["CPI"]})
    out = cc.filter_events(fomc, cont)
    assert len(out["included"]) == 1 and len(out["excluded"]) == 0


def test_fed_communication_flag_baseline_vs_robust():
    # `is_fed_speech_major(t)` ritorna True per testimony/discorso Fed nel periodo.
    fomc = pd.DataFrame({"event_time": pd.to_datetime(["2021-06-16 18:00"], utc=True)})
    fed_major = pd.to_datetime(["2021-06-17 14:00"], utc=True)
    out_baseline = cc.filter_events(fomc, contaminants=pd.DataFrame(
        {"time": pd.to_datetime([], utc=True), "kind": []}))
    out_robust = cc.filter_events(
        fomc,
        contaminants=pd.DataFrame({"time": pd.to_datetime([], utc=True), "kind": []}),
        fed_major_speeches=fed_major,
        mode="robust_drop_fed_t1",
    )
    # baseline: l'evento è incluso (la spec dice: comunicazione Fed in T+1 è
    # PARTE dello spillover nel baseline)
    assert len(out_baseline["included"]) == 1
    # robust: l'evento è rimosso perché c'è un intervento Fed major in T+1
    assert len(out_robust["included"]) == 0
    assert "FED_T1" in set(out_robust["excluded"]["reason"].astype(str))


def test_manifest_records_inputs_and_counts():
    fomc = pd.DataFrame({"event_time": pd.to_datetime(["2021-06-16 18:00"], utc=True)})
    out = cc.filter_events(fomc, contaminants=pd.DataFrame(
        {"time": pd.to_datetime([], utc=True), "kind": []}))
    m = cc.manifest(out)
    assert m["n_included"] == 1 and m["n_excluded"] == 0
    assert "mode" in m and m["mode"] == "baseline"

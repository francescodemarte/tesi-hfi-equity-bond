"""Test integrazione: orchestratore, blocco main, struttura output."""
import pandas as pd
import pytest

import config
import run
import synthetic


def test_main_is_blocked():
    with pytest.raises(SystemExit):
        run.main()


def test_run_strategy_requires_columns():
    bad = pd.DataFrame({"date": [pd.Timestamp("2015-01-01")]})
    with pytest.raises(ValueError):
        run.run_strategy(bad)


def test_run_strategy_output_contains_required_sections():
    rng = config.make_rng("integ")
    df = synthetic.dgp_signal(rng, n_train=200, n_test=100)
    out = run.run_strategy(df)
    for k in ("calibration", "training_metrics", "test_metrics",
              "split_date", "config_hash", "n_train", "n_test"):
        assert k in out


def test_run_strategy_reports_per_cell_counts():
    rng = config.make_rng("integ2")
    df = synthetic.dgp_signal(rng, n_train=200, n_test=100)
    out = run.run_strategy(df)
    test_m = out["test_metrics"]
    for leg in config.LEGS:
        for reg in ("pos", "neg"):
            assert "n" in test_m[(leg, reg)]
            assert "verdict" in test_m[(leg, reg)]["strategy"]


def test_run_strategy_wires_intra_event_lookahead_check_when_calendar_passed():
    """REVIEW #1: se l'esecutore passa il calendario, run_strategy DEVE invocare
    three_windows + assert_no_lookahead per ciascun evento — wiring del presidio.

    Costruisco un calendario business e ALLINEO ogni data-evento al business
    day immediatamente precedente, perché il vero "calendario di mercato"
    dell'esecutore conterrà solo sedute (lun–ven, festivi esclusi); le date
    evento del DGP cadute di sabato/domenica vanno allineate prima del wiring.
    """
    rng = config.make_rng("wire_la")
    df = synthetic.dgp_signal(rng, n_train=200, n_test=100).copy()
    df["date"] = pd.to_datetime(df["date"]) + pd.tseries.offsets.BusinessDay(0)   # snap a business day
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    # calendario business con buffer per coprire 63+4 sedute prima di ogni evento
    cal = pd.bdate_range(df["date"].min() - pd.Timedelta(days=200),
                          df["date"].max() + pd.Timedelta(days=5))
    cal_norm = [c.normalize() for c in cal]
    cal_idx = {d: i for i, d in enumerate(cal_norm)}
    # event_to_idx: indice del business day dell'evento nel calendario
    ev2idx = {d.normalize(): cal_idx[d.normalize()] for d in df["date"]
              if d.normalize() in cal_idx}
    out = run.run_strategy(df, event_calendar={"calendar": list(cal),
                                                "event_to_idx": ev2idx})
    assert out["intra_event_lookahead_check"] == "validated"


def test_run_strategy_marks_delegated_when_calendar_absent():
    """REVIEW #1: senza calendario, il manifest dichiara `delegated_to_executor`."""
    rng = config.make_rng("delegated")
    df = synthetic.dgp_signal(rng, n_train=200, n_test=100)
    out = run.run_strategy(df)
    assert out["intra_event_lookahead_check"] == "delegated_to_executor"


def test_run_strategy_raises_if_calendar_implies_lookahead():
    """REVIEW #1: presidio strutturale: un calendario incoerente (event_idx
    troppo basso per coprire 63+4 sedute) DEVE far sollevare run_strategy."""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2010-01-15", "2022-06-10"]),
        "leg": ["NFP", "NFP"], "regime": ["pos", "neg"],
        "epsilon": [0.1, 0.2],
    })
    # Calendario troppo corto: event_idx=0 ⇒ regime non ha 63 sedute prima
    short_cal = pd.bdate_range("2010-01-01", "2010-01-20")
    bad_map = {pd.Timestamp("2010-01-15"): 10,
                pd.Timestamp("2022-06-10"): 12}    # 12 < 67 ⇒ regime non costruibile
    with pytest.raises(ValueError):
        run.run_strategy(df, event_calendar={"calendar": list(short_cal),
                                              "event_to_idx": bad_map})


def test_run_strategy_raises_on_empty_train_or_test():
    df_only_train = pd.DataFrame({
        "date": pd.date_range("2015-01-01", periods=10),
        "leg": ["NFP"] * 10, "regime": ["pos"] * 10,
        "epsilon": [0.1] * 10,
    })
    with pytest.raises(ValueError):
        run.run_strategy(df_only_train)

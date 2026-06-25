"""Test di integrazione END-TO-END su DGP sintetico.

Esercita `run.run_protocol_full` e ne valida la COMPLETEZZA dell'output:
T1, T2, T3, T4, T5, T6, T7 (criteri esogeni), T8 (a/c/d), T9, decomposizione
daily, e manifest scritto. Il presidio è proprio la completezza: un orchestratore
incompleto (mancante di T7/T8/T9/decomp/manifest) deve far fallire questo test.

Niente dati reali: DGP sintetico (`synthetic.dgp_structural_flip`).
"""
import json

import numpy as np
import pandas as pd

import config
import run
import synthetic


def _exogenous_daily(rng, name, n=400, start="2020-01-01"):
    """Serie macro daily sintetica (per T7) con due regimi netti."""
    idx = pd.date_range(start, periods=n, freq="B")
    half = n // 2
    s = np.concatenate([rng.normal(-1, 0.3, half), rng.normal(+1, 0.3, n - half)])
    return pd.Series(s, index=idx, name=name)


def _cpi_yoy_monthly():
    """CPI YoY daily-ish (mensile); pre-2022 sotto soglia, 2022+ sopra."""
    months = pd.date_range("2018-01-31", "2025-12-31", freq="ME")
    yoy = np.where(months.year >= 2022, 0.08, 0.02)
    return pd.Series(yoy, index=months, name="cpi_yoy")


def test_e2e_run_protocol_full_produces_all_sections(tmp_path):
    rng_dgp = np.random.default_rng(7)
    per_type_clusters = synthetic.dgp_structural_flip(rng_dgp, n_events=80)

    # aggiungo center+meta a ogni cluster (l'orchestratore reale li usa).
    # PRESIDIO post Bug 1 (Esecutore 2026-06-22): inietto date DUPLICATE per
    # esercitare il pattern reale (FOMC decision+press conf stesso giorno,
    # FOMC+CPI sovrapposti) — il bug nei dati reali era invisibile al fixture
    # precedente che generava tutte date distinte.
    base_dates = pd.date_range("2019-01-01", periods=80, freq="MS")
    for t, cells in per_type_clusters.items():
        for reg in ("pos", "neg"):
            for i, cl in enumerate(cells[reg]):
                # NFP: ogni 5° evento condivide la data col precedente (≈ FOMC
                # decision+press stesso giorno → 2 record). Altri tipi: date distinte.
                d = base_dates[(i // 2) if (t == "NFP" and i % 5 == 0) else i] \
                    + pd.Timedelta(days={"pos": 1, "neg": 15}[reg])
                # PRESIDIO post Bug 2 (Esecutore 2026-06-22): NFP e ECB hanno
                # center TZ-AWARE UTC (come `events["timestamp"]` dei dati reali);
                # CPI/FOMC restano tz-naive (mix patologie nello stesso fixture).
                if t in ("NFP", "ECB"):
                    d = pd.Timestamp(d).tz_localize("UTC") + pd.Timedelta(hours=18)
                cl["event"]["center"] = d
                cl["meta"] = {"year": pd.Timestamp(d).year}

    rng_exo = np.random.default_rng(42)
    exo_series = {nm: _exogenous_daily(rng_exo, nm) for nm in config.T7_EXOGENOUS_REQUIRED}
    cpi_yoy = _cpi_yoy_monthly()

    out = run.run_protocol_full(
        per_type_clusters,
        rng=config.make_rng("e2e"),
        exogenous_series=exo_series,
        cpi_yoy=cpi_yoy,
        manifest_path=tmp_path / "manifest.json",
        manifest_timestamp="2026-06-22T00:00:00Z",
        B=120,
    )

    # ─── presidio Bug 1: la fixture DEVE contenere date duplicate ───
    nfp_dates = [cl["event"]["center"] for cl in per_type_clusters["NFP"]["pos"]]
    assert len(nfp_dates) > len(set(nfp_dates)), \
        "fixture e2e deve avere date duplicate (presidio Bug 1)"

    # ─── presidio Bug 2: la fixture DEVE contenere almeno un center tz-aware ───
    has_tz_aware = any(getattr(pd.Timestamp(c), "tz", None) is not None
                        for cl in per_type_clusters["NFP"]["pos"]
                        for c in [cl["event"]["center"]])
    assert has_tz_aware, "fixture e2e deve avere almeno un center tz-aware UTC (presidio Bug 2)"

    # ─── completezza dell'output (presidio centrale) ───
    for section in ("cv_mop", "routing", "t3", "t4", "t5", "t6", "t7", "t8", "t9",
                    "decomposition", "dedup_shared", "shared_control", "manifest"):
        assert section in out, f"missing section: {section}"

    # T1 instrada
    assert "NFP" in out["routing"]
    # T5 rileva il flip strutturale di NFP nel DGP A
    assert out["t5"]["flip_detected"]["NFP"] is True

    # T7: una voce per criterio esogeno (almeno T10Y2Y, VIXCLS)
    for c in config.T7_EXOGENOUS_REQUIRED:
        assert c in out["t7"], f"T7 missing criterion: {c}"
        assert "flip_detected" in out["t7"][c]

    # T8: 4 perturbazioni (a/c/d + baseline)
    assert {"baseline", "exclude_extreme", "widen_regime", "exclude_inflationary"} <= set(out["t8"])

    # T9: meccanismo presente, può essere gated (no surprise s ⇒ struttura None ammessa)
    assert out["t9"] is None or isinstance(out["t9"], dict)

    # decomposizione daily presente (può essere None se input non disponibile in e2e)
    assert "decomposition" in out

    # manifest scritto su disco con config_hash + entries
    assert (tmp_path / "manifest.json").exists()
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert m["config_hash"] == config.config_hash()
    assert isinstance(m.get("entries"), list)

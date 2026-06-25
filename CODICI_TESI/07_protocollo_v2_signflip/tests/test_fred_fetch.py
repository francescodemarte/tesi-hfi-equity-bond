"""Test fred_fetch — parsing CSV FRED, derivazione YoY da livello, write con provenienza.

NIENTE RETE REALE: i test costruiscono CSV mock (formato pubblico FRED:
fredgraph.csv è `DATE,SERIES_ID`) e verificano il parser + il freeze su disco.
"""
import json
import pathlib
import pandas as pd
import pytest

import fred_fetch as ff


# --- parsing del formato fredgraph.csv (DATE, VALUE) -------------------

def test_parse_fred_csv_handles_dots_as_missing(tmp_path):
    p = tmp_path / "DGS10.csv"
    p.write_text("DATE,DGS10\n2020-01-02,2.50\n2020-01-03,.\n2020-01-06,2.55\n")
    s = ff.parse_fredgraph_csv(p, "DGS10")
    assert s.index[0] == pd.Timestamp("2020-01-02")
    assert s.iloc[0] == pytest.approx(2.50)
    assert pd.isna(s.iloc[1])
    assert s.iloc[2] == pytest.approx(2.55)
    assert s.name == "DGS10"


# --- derivazione YoY da livello mensile (CPIAUCSL → YoY) ---------------

def test_cpi_yoy_from_level_uses_12m_pct_change():
    idx = pd.date_range("2020-01-01", periods=24, freq="MS")
    lvl = pd.Series(100.0 * (1.03 ** (pd.Series(range(24)) / 12.0)).values, index=idx,
                    name="CPIAUCSL")   # ~3% YoY annualizzato
    yoy = ff.cpi_yoy_from_level(lvl)
    # primi 12 mesi: NaN (manca il riferimento a 12m fa)
    assert yoy.iloc[:12].isna().all()
    # YoY ≈ 3% a regime
    assert yoy.iloc[-1] == pytest.approx(0.03, abs=1e-3)


# --- freeze con provenienza --------------------------------------------

def test_freeze_writes_csv_plus_provenance(tmp_path):
    s = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2020-01-01", periods=3), name="X")
    out = ff.freeze_series(s, tmp_path, name="X",
                           source_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=X",
                           fetched_at="2026-06-22T00:00:00Z")
    assert pathlib.Path(out["csv_path"]).exists()
    assert pathlib.Path(out["provenance_path"]).exists()
    prov = json.loads(pathlib.Path(out["provenance_path"]).read_text())
    assert prov["name"] == "X"
    assert prov["source_url"].endswith("id=X")
    assert prov["fetched_at"] == "2026-06-22T00:00:00Z"
    assert "sha256" in prov                                  # hash del CSV congelato
    assert prov["n_rows"] == 3
    assert prov["date_min"] == "2020-01-01"
    assert prov["date_max"] == "2020-01-03"


# --- contratto: l'elenco delle release FRED che servono al calendario ---

def test_us_release_series_contains_all_required_contaminants():
    needed = {"CPI", "PPI", "RETAIL", "GDP", "PCE", "DURABLE", "JOBLESS"}
    assert needed <= set(ff.US_RELEASE_SERIES.keys())
    # ogni voce ha una series id stringa (mnemonica FRED)
    for k, v in ff.US_RELEASE_SERIES.items():
        assert isinstance(v, str) and len(v) >= 2

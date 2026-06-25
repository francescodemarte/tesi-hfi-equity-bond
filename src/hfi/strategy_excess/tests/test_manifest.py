"""Test manifest: provenance + replicability note + counts."""
import json
from pathlib import Path

import pandas as pd
import pytest

import config
import manifest
import run
import synthetic


def test_manifest_seed_includes_integer_value():
    """REVIEW #2: due esecutori con stesso seed_name devono poter VERIFICARE
    di aver usato lo stesso intero — non solo il nome."""
    rng = config.make_rng("m_seed")
    df = synthetic.dgp_signal(rng, n_train=80, n_test=40)
    out = run.run_strategy(df)
    m = manifest.build_manifest(
        run_output=out, input_paths=[], code_paths=[],
        seed_name="real_run_2026-06-22", timestamp="T",
    )
    assert "value" in m["seed"]
    assert m["seed"]["value"] == config.seed_for("real_run_2026-06-22")
    assert isinstance(m["seed"]["value"], int)


def test_manifest_records_required_fields(tmp_path):
    rng = config.make_rng("manifest")
    df = synthetic.dgp_signal(rng, n_train=200, n_test=100)
    out = run.run_strategy(df)
    fake_input = tmp_path / "events.csv"; fake_input.write_text("x\n1\n")
    m = manifest.build_manifest(
        run_output=out,
        input_paths=[fake_input],
        code_paths=[Path(__file__).resolve().parent.parent / "run.py"],
        seed_name="real_run_2026-06-22",
        timestamp="2026-06-22T12:00:00Z",
    )
    for k in ("config_version", "config_hash", "split_date", "cell_counts",
              "calibration_e_gk", "seed", "inputs", "code",
              "replicability_assumption", "timestamp"):
        assert k in m
    assert m["inputs"][0]["sha256"] is not None
    assert m["timestamp"] == "2026-06-22T12:00:00Z"
    assert "covariance-swap" in m["replicability_assumption"].lower()


def test_manifest_marks_missing_input(tmp_path):
    rng = config.make_rng("manifest_miss")
    df = synthetic.dgp_signal(rng, n_train=200, n_test=100)
    out = run.run_strategy(df)
    m = manifest.build_manifest(
        run_output=out,
        input_paths=[tmp_path / "nonexistent.csv"],
        code_paths=[],
        seed_name="x", timestamp="T",
    )
    assert m["inputs"][0]["status"].startswith("missing")
    assert m["inputs"][0]["sha256"] is None


def test_write_manifest_roundtrip(tmp_path):
    rng = config.make_rng("manifest_rt")
    df = synthetic.dgp_signal(rng, n_train=200, n_test=100)
    out = run.run_strategy(df)
    m = manifest.build_manifest(
        run_output=out, input_paths=[], code_paths=[],
        seed_name="x", timestamp="T")
    out_path = tmp_path / "manifest.json"
    sha = manifest.write_manifest(out_path, m)
    assert out_path.exists() and len(sha) == 64
    loaded = json.loads(out_path.read_text())
    assert loaded["config_hash"] == config.config_hash()

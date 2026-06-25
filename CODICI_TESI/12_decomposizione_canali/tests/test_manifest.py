"""Test manifest: pattern uniforme con 07/08/11 (REVIEW #1)."""
import json
from pathlib import Path

import pytest

import config
import manifest


def test_build_manifest_records_required_fields(tmp_path):
    fake_in = tmp_path / "events.csv"; fake_in.write_text("a\n1\n")
    cell_outputs = {
        ("NFP", "neg"): {"n": 50, "gate_a": "PASS", "verdict": "identified_robust",
                          "beta_str_central": 1.5},
        ("NFP", "pos"): {"n": 10, "gate_a": "FAIL", "verdict": "channel_not_identified",
                          "beta_str_central": float("nan")},
    }
    m = manifest.build_manifest(
        cell_outputs=cell_outputs,
        input_paths=[fake_in],
        code_paths=[],
        seed_name="run_2026-06-22",
        timestamp="2026-06-22T12:00:00Z",
    )
    for k in ("config_version", "config_hash", "seed", "inputs",
              "cell_counts", "verdicts_per_cell", "replicability_assumption",
              "timestamp"):
        assert k in m
    # seed.value DEVE essere l'intero deterministico (pattern 07/08/11)
    assert m["seed"]["name"] == "run_2026-06-22"
    assert m["seed"]["value"] == config.seed_for("run_2026-06-22")
    assert isinstance(m["seed"]["value"], int)
    # config_hash è l'hash dello snapshot CONGELATO (entra band_width_threshold ora)
    assert m["config_hash"] == config.config_hash()
    # cell_counts per provenance
    assert m["cell_counts"] == {"NFP/neg": 50, "NFP/pos": 10}
    # verdicts esposti
    assert m["verdicts_per_cell"]["NFP/neg"] == "identified_robust"


def test_build_manifest_replicability_assumption_explicit():
    m = manifest.build_manifest(cell_outputs={}, input_paths=[], code_paths=[],
                                seed_name="x", timestamp="T")
    # La spec impone di dichiarare gli assunti (Campbell-Shiller, dp_bar, coda)
    text = m["replicability_assumption"].lower()
    assert "campbell" in text or "log-lin" in text
    assert "dp_bar" in text or "rho" in text or "ρ" in text
    assert "coda" in text or "tail" in text


def test_build_manifest_marks_missing_input(tmp_path):
    m = manifest.build_manifest(
        cell_outputs={}, input_paths=[tmp_path / "nonexistent.csv"],
        code_paths=[], seed_name="x", timestamp="T")
    assert m["inputs"][0]["status"].startswith("missing")
    assert m["inputs"][0]["sha256"] is None


def test_build_manifest_timestamp_is_external_required():
    with pytest.raises(TypeError):
        manifest.build_manifest(cell_outputs={}, input_paths=[], code_paths=[],
                                 seed_name="x")    # manca timestamp


def test_write_manifest_roundtrip(tmp_path):
    m = manifest.build_manifest(cell_outputs={}, input_paths=[], code_paths=[],
                                 seed_name="x", timestamp="T")
    out = tmp_path / "sub" / "m.json"
    sha = manifest.write_manifest(out, m)
    assert out.exists() and len(sha) == 64
    loaded = json.loads(out.read_text())
    assert loaded["config_hash"] == config.config_hash()

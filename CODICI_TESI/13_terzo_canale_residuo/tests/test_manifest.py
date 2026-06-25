"""Test manifest: provenance + replicability + verdicts (pattern uniforme)."""
import json
from pathlib import Path

import pytest

import config
import manifest
import pipeline as P
import synthetic as S


def _fake_run_output():
    rng = config.make_rng("manifest_dummy")
    dgp = S.dgp_case2_no_third_channel(rng, n=300)
    inputs = {tuple(c): {"r_e_tilde": dgp["r_e_tilde"], "r_b_tilde": dgp["r_b_tilde"],
                          "beta_str": 1.0, "surprise": dgp["s"]}
              for c in config.ROBUST_CELLS}
    proxies = {tuple(c): {k: {"z": dgp["z"], "expected_sign": config.EXPECTED_SIGN[k]}
                          for k in config.CANDIDATES}
               for c in config.ROBUST_CELLS}
    return P.run_full_protocol(inputs, proxies)


def test_manifest_includes_pattern_fields(tmp_path):
    out = _fake_run_output()
    fake = tmp_path / "input.csv"; fake.write_text("a\n1\n")
    m = manifest.build_manifest(
        run_output=out, input_paths=[fake], code_paths=[],
        seed_name="real_run_2026-06-23",
        timestamp="2026-06-23T12:00:00Z",
    )
    for k in ("config_version", "config_hash", "seed", "inputs",
              "by", "third_channel_findings", "replicability_assumption",
              "timestamp"):
        assert k in m
    assert m["seed"]["value"] == config.seed_for("real_run_2026-06-23")
    assert m["config_hash"] == config.config_hash()
    assert m["inputs"][0]["sha256"] is not None
    # Replicability cita i 3 candidati e i 6 punti
    text = m["replicability_assumption"]
    assert "L" in text and "V" in text and "C" in text


def test_manifest_records_third_channel_findings_keys():
    out = _fake_run_output()
    m = manifest.build_manifest(run_output=out, input_paths=[], code_paths=[],
                                 seed_name="x", timestamp="T")
    # 12 chiavi cell/candidate
    assert len(m["third_channel_findings"]) == 12
    for k in m["third_channel_findings"]:
        assert "/" in k   # formato "leg/regime/candidate"


def test_manifest_timestamp_external_required():
    with pytest.raises(TypeError):
        manifest.build_manifest(run_output={}, input_paths=[], code_paths=[],
                                 seed_name="x")


def test_write_manifest_roundtrip(tmp_path):
    out = _fake_run_output()
    m = manifest.build_manifest(run_output=out, input_paths=[], code_paths=[],
                                 seed_name="x", timestamp="T")
    path = tmp_path / "m.json"
    sha = manifest.write_manifest(path, m)
    assert path.exists() and len(sha) == 64
    loaded = json.loads(path.read_text())
    assert loaded["config_hash"] == config.config_hash()

"""Test di provenance.py (C0.6, R4) — TDD stretto.

Verifica: hashing deterministico = hashlib; voce di manifest registra
script+input+seed+config; il manifest fa round-trip su json; il timestamp è
quello passato (nessun clock interno).
"""
import hashlib
import json

import pandas as pd

import config
import provenance


def test_file_sha256_matches_hashlib(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"hello world")
    assert provenance.file_sha256(p) == hashlib.sha256(b"hello world").hexdigest()


def test_text_sha256_matches_hashlib():
    assert provenance.text_sha256("abc") == hashlib.sha256(b"abc").hexdigest()


def test_make_entry_records_script_inputs_seed_config(tmp_path):
    script = tmp_path / "run.py"
    script.write_bytes(b"print(1)")
    inp = tmp_path / "data.csv"
    inp.write_bytes(b"a,b\n1,2\n")

    entry = provenance.make_entry(
        figure="T5_signflip_table",
        script=script,
        inputs=[inp],
        seed_name="t5_signflip",
        timestamp="2026-06-21T00:00:00Z",
    )

    assert entry["figure"] == "T5_signflip_table"
    assert entry["script"]["sha256"] == hashlib.sha256(b"print(1)").hexdigest()
    assert entry["inputs"][0]["sha256"] == hashlib.sha256(b"a,b\n1,2\n").hexdigest()
    # il seed dichiarato coincide con lo schema di config
    assert entry["seed"]["name"] == "t5_signflip"
    assert entry["seed"]["value"] == config.seed_for("t5_signflip")
    assert entry["config_hash"] == config.config_hash()
    assert entry["config_version"] == config.CONFIG_VERSION
    # timestamp = quello passato (no clock interno)
    assert entry["timestamp"] == "2026-06-21T00:00:00Z"


def test_make_entry_handles_multiple_inputs(tmp_path):
    a = tmp_path / "a.csv"; a.write_bytes(b"AA")
    b = tmp_path / "b.csv"; b.write_bytes(b"BB")
    entry = provenance.make_entry(figure="f", script=a, inputs=[a, b],
                                  seed_name="s", timestamp="T")
    paths = [i["path"] for i in entry["inputs"]]
    assert str(a) in paths and str(b) in paths
    assert len(entry["inputs"]) == 2


def test_control_accounting_record_summarizes_drops():
    assembled = {
        "n_controls": 4,
        "dropped": [
            {"center": pd.Timestamp("2021-06-08 12:30:00", tz="UTC"), "reason": "calendar"},
            {"center": pd.Timestamp("2021-06-07 12:30:00", tz="UTC"), "reason": "no_data_eq"},
        ],
    }
    rec = provenance.control_accounting_record("NFP@2021-06-09", assembled)
    assert rec["event"] == "NFP@2021-06-09"
    assert rec["n_controls"] == 4
    assert {d["reason"] for d in rec["dropped"]} == {"calendar", "no_data_eq"}
    # i center sono serializzati come stringhe (json-safe)
    assert all(isinstance(d["center"], str) for d in rec["dropped"])


def test_write_manifest_with_diagnostics(tmp_path):
    script = tmp_path / "r.py"; script.write_bytes(b"x")
    inp = tmp_path / "d.csv"; inp.write_bytes(b"y")
    entry = provenance.make_entry(figure="f", script=script, inputs=[inp],
                                  seed_name="s", timestamp="T")
    diag = {"control_accounting": [{"event": "NFP@x", "n_controls": 5, "dropped": []}]}
    out = tmp_path / "m.json"
    m = provenance.write_manifest(out, [entry], timestamp="T", diagnostics=diag)
    loaded = json.loads(out.read_text())
    assert loaded["diagnostics"]["control_accounting"][0]["event"] == "NFP@x"
    assert m["diagnostics"] == diag


def test_write_manifest_roundtrip(tmp_path):
    script = tmp_path / "run.py"; script.write_bytes(b"x")
    inp = tmp_path / "d.csv"; inp.write_bytes(b"y")
    entry = provenance.make_entry(figure="f", script=script, inputs=[inp],
                                  seed_name="s", timestamp="T")
    out = tmp_path / "sub" / "manifest.json"  # cartella non esistente → dev'essere creata

    manifest = provenance.write_manifest(out, [entry], timestamp="2026-06-21T00:00:00Z")

    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["config_hash"] == config.config_hash()
    assert loaded["config_version"] == config.CONFIG_VERSION
    assert loaded["generated"] == "2026-06-21T00:00:00Z"
    assert loaded["entries"][0]["figure"] == "f"
    assert manifest["entries"][0]["seed"]["value"] == config.seed_for("s")

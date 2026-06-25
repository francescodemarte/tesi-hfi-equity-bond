"""fred_fetch.py — Procurement degli input FRED (autorizzato).

Scarica le serie macro USA via il graph endpoint pubblico di FRED
(`fredgraph.csv?id=<SERIES>`) e LE CONGELA su disco con provenienza
(URL, timestamp del fetch, sha256 del CSV, range temporale, n. righe).

Procurement, NON analisi: nessuna stima è eseguita qui. L'esecutore consuma
gli snapshot congelati. Le serie scaricate sono SOLO quelle dichiarate nei
parametri E3 + calendario US lato FRED (lista pubblicata in `US_RELEASE_SERIES`).

Fonti non-FRED del calendario (TreasuryDirect, Fed Board, BCE, Bundesbank/MEF/AFT)
NON sono qui — vanno autorizzate separatamente e procurate altrove.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import urllib.request
import urllib.error
from io import StringIO
from pathlib import Path

import pandas as pd

# --- E3: serie obbligatorie ------------------------------------------------
T7_REQUIRED_SERIES = ("T10Y2Y", "VIXCLS")                  # + MOVE se autorizzato
T8D_CPI_LEVEL = "CPIAUCSL"                                  # → YoY via 12m pct-change

# --- Calendario US (lato FRED): contaminanti delle finestre 08:30 ET -------
# Si scaricano i livelli pubblicati: le DATE di rilascio = l'INDICE temporale
# dei DataPoint, perché FRED pubblica al giorno-rilascio. (Per CPI/PPI/jobless
# l'allineamento è puntuale; per GDP è la stima trimestrale; per altre il timing
# è documentato e l'esecutore lo affina.)
US_RELEASE_SERIES = {
    "CPI": "CPIAUCSL",          # CPI All Items, livello
    "PPI": "PPIACO",            # PPI All Commodities
    "RETAIL": "RSAFS",          # Retail Sales (Advance)
    "GDP": "GDP",               # GDP, livello trimestrale
    "PCE": "PCEPI",             # PCE Price Index
    "DURABLE": "DGORDER",       # Durable Goods Orders
    "JOBLESS": "ICSA",          # Initial Claims (settimanali, giovedì)
}

_FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def parse_fredgraph_csv(path_or_text, series_id: str) -> pd.Series:
    """Parser di `fredgraph.csv`: prima colonna data (`DATE` o `observation_date`,
    a seconda della versione FRED), seconda colonna `<series_id>`. `.` = NaN.
    """
    if isinstance(path_or_text, Path):
        text = path_or_text.read_text()
    elif isinstance(path_or_text, str) and len(path_or_text) < 4096 and "\n" not in path_or_text:
        # path testuale ragionevolmente corto e senza newline → tratta come path
        p = Path(path_or_text)
        text = p.read_text() if p.exists() else path_or_text
    else:
        text = path_or_text  # già contenuto CSV
    df = pd.read_csv(StringIO(text), na_values=["."])
    date_col = None
    for cand in ("DATE", "observation_date"):
        if cand in df.columns:
            date_col = cand; break
    if date_col is None:
        date_col = df.columns[0]    # fallback: prima colonna
    if series_id not in df.columns:
        raise ValueError(f"colonna {series_id!r} assente nel CSV (colonne: {list(df.columns)})")
    df[date_col] = pd.to_datetime(df[date_col])
    s = df.set_index(date_col)[series_id]
    s.name = series_id
    s.index.name = "DATE"
    return s


def cpi_yoy_from_level(level: pd.Series) -> pd.Series:
    """YoY da livello mensile: r_t = level_t / level_{t-12} − 1 (T8D, E3)."""
    s = level.sort_index()
    return s.pct_change(12, fill_method=None).rename("CPI_YoY")


def fetch_series(series_id: str, *, cache_dir: Path | None = None,
                 timeout: int = 90) -> tuple[str, str]:
    """Scarica `series_id` dal graph FRED; restituisce (testo_csv, source_url).

    `cache_dir` (se passato) abilita una cache su disco per i ri-tentativi
    (la cache NON è uno snapshot congelato: l'output ufficiale è prodotto da
    `freeze_series`).
    """
    url = _FRED_URL.format(sid=series_id)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        c = cache_dir / f"{series_id}.csv"
        if c.exists():
            return c.read_text(), url
    # Ordine preferito: wget (sub-stack HTTP/1.1, stabile da subprocess) → curl →
    # urllib (HTTP/2 da subprocess è instabile su questo host).
    if shutil.which("wget"):
        text = _fetch_via_wget(url, timeout=timeout)
    elif shutil.which("curl"):
        text = _fetch_via_curl(url, timeout=timeout)
    else:
        text = _fetch_via_urllib(url, timeout=timeout)
    if cache_dir is not None:
        (cache_dir / f"{series_id}.csv").write_text(text)
    return text, url


def _fetch_via_wget(url: str, *, timeout: int) -> str:
    """Backend wget (preferito da subprocess: HTTP/1.1 stabile su questo host)."""
    res = subprocess.run(
        ["wget", "-q", "-O", "-", "--timeout", str(timeout),
         "--tries", "3", "--waitretry", "2",
         "--user-agent=agente3-procurement/1.0", url],
        capture_output=True, text=True, check=False,
    )
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError(f"wget fallito ({res.returncode}): {res.stderr.strip()[:200]}")
    return res.stdout


def _fetch_via_curl(url: str, *, timeout: int) -> str:
    """Backend di rete via `curl` (più tollerante a policy/TLS del sandbox).

    Forzato HTTP/1.1 (alcuni stream HTTP/2 risultano instabili su questo host)
    + retry esponenziale a livello curl.
    """
    res = subprocess.run(
        ["curl", "-sSL", "--max-time", str(timeout),
         "--retry", "3", "--retry-delay", "2",
         "-H", "User-Agent: agente3-procurement/1.0", url],
        capture_output=True, text=True, check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"curl fallito ({res.returncode}): {res.stderr.strip()[:200]}")
    return res.stdout


def _fetch_via_urllib(url: str, *, timeout: int) -> str:
    """Fallback urllib (usato se `curl` non è disponibile)."""
    req = urllib.request.Request(url, headers={"User-Agent": "agente3-procurement/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def freeze_series(series: pd.Series, snapshot_dir: Path, *, name: str,
                  source_url: str, fetched_at: str) -> dict:
    """Congela la serie + provenienza: <snapshot_dir>/<name>.csv + <name>.provenance.json.

    `fetched_at`: timestamp ISO PASSATO DALL'ESTERNO (no clock interno).
    Provenienza: source_url, fetched_at, sha256 del CSV, n. righe, range temporale.
    """
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    csv_path = snapshot_dir / f"{name}.csv"
    series.to_csv(csv_path, index_label="DATE", header=[name])
    payload = csv_path.read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    prov = {
        "name": name, "source_url": source_url, "fetched_at": fetched_at,
        "sha256": sha, "n_rows": int(len(series)),
        "date_min": str(series.index.min().date()),
        "date_max": str(series.index.max().date()),
    }
    prov_path = snapshot_dir / f"{name}.provenance.json"
    prov_path.write_text(json.dumps(prov, indent=2, sort_keys=True))
    return {"csv_path": str(csv_path), "provenance_path": str(prov_path), "provenance": prov}


def procurement_plan() -> list[dict]:
    """Lista delle serie da scaricare (E3 + calendario US lato FRED)."""
    plan = [{"series_id": s, "purpose": f"E3 T7 ({s})"} for s in T7_REQUIRED_SERIES]
    plan += [{"series_id": T8D_CPI_LEVEL, "purpose": "E3 T8(d): CPI YoY da livello"}]
    plan += [{"series_id": v, "purpose": f"calendario US contaminante: {k}"}
             for k, v in US_RELEASE_SERIES.items() if v != T8D_CPI_LEVEL]
    # dedup mantenendo l'ordine
    seen, out = set(), []
    for it in plan:
        if it["series_id"] in seen:
            continue
        seen.add(it["series_id"]); out.append(it)
    return out

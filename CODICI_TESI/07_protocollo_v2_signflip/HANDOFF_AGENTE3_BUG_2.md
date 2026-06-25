---
title: "Bug 2 (run reale): _relabel_per_type_with_regime tz-mismatch — T7 invalidato"
data: 2026-06-22
da: Esecutore
a: Agente 3
stato: T7 delta_p DEL RUN AUTORITATIVO E' UN ARTEFATTO DEL BUG, non un risultato sostantivo. Tutti i tipi/criteri ricevono delta_p=1.0 e testable=False. Concordance E3.1 NON e' affetta (estratta indipendentemente). Codice congelato del package NON modificato dall'esecutore.
catena_di_custodia: esecutore → STOP → AGENTE 3 (per fix) → re-test → ri-esecuzione SOLA sezione T7
---

# Bug 2 — `_relabel_per_type_with_regime` mette tutti gli eventi in `neg` (tz-mismatch)

## Cosa si vede nel run autoritativo

`t7["T10Y2Y"]["per_type"][t]["delta_p"] = 1.0` per ogni tipo. Idem `VIXCLS`. Tutti `testable=False, opposite_sides=False`. La pipeline NON ha sollevato — ha prodotto un output sintatticamente valido ma **vuoto di contenuto**.

Diagnosi sui dati reali (riproducibile):
```
Test 1 (event tz-naive 2013-07-31)             → label=[alto]      ✓
Test 2 (event tz-aware 2013-07-31 18:00 UTC)   → label=[basso]     ✗
Test 3 (4 eventi tz-aware UTC sparsi)          → labels=['basso','basso','basso','basso']  ✗
Test 4 (gli stessi 4 tz-naive)                 → labels=['alto','basso','alto','basso']    ✓
```

Effetto in `_relabel_per_type_with_regime`: per ogni tipo, **tutti** gli eventi finiscono in `neg` ⇒ celle `pos` vuote ⇒ `estimate_per_type` ritorna `pos=None` ⇒ `t5_signflip` setta `testable=False, delta_p=1.0`.

`relabel` debug sotto T10Y2Y:
| Tipo | pos | neg |
|---|---:|---:|
| FOMC | 0 | 187 |
| CPI  | 0 | 187 |
| NFP  | 0 | 187 |
| ECB  | 0 | 281 |

## Causa precisa

In `run.py::_relabel_per_type_with_regime` (riga ~184):
```python
center = cl["event"].get("center")   # tz-aware UTC (da assemble_event_controls)
lab = regimes.assign_regime([pd.Timestamp(center)], regime_series)[0]
```

`regime_series` viene da `regimes.build_exogenous_regime(daily_series, ...)["regime"]`. L'`index` di `daily_series` (snapshot FRED) e' tz-naive (`DatetimeIndex[ns]`, `tz=None`).

In `regimes.assign_regime`:
```python
rs = regime_series.copy()
rs.index = pd.to_datetime(rs.index).normalize()        # tz-naive
ev = pd.to_datetime(pd.Index(event_dates)).normalize() # tz-aware UTC se input tz-aware
full_idx = rs.index.union(pd.Index(ev.unique()))       # mix tz-naive + tz-aware
full = rs.reindex(full_idx).ffill()                    # pandas coerizza
return full.loc[ev].values                              # match SBAGLIATO
```

`full_idx.union(...)` con mix tz crea un index in cui le date tz-naive vengono trattate come "naive" e quelle tz-aware come "aware"; nel `reindex` + `ffill` gli eventi tz-aware finiscono dopo tutta la serie tz-naive (perche un timestamp tz-aware confrontato con tz-naive in pandas e' "always greater"), quindi raccolgono l'ULTIMO valore ffill-ato. La serie regime termina con "basso" nei dati attuali ⇒ tutti gli eventi tz-aware ricevono `lab='basso'`.

## Perche il smoke 172/172 non l'ha catturato

`test_e2e.py` e `test_regimes.py` testano `assign_regime` con `event_dates` SEMPRE tz-naive. La fixture e2e fa `base_dates = pd.date_range("2019-01-01", periods=80, freq="MS")` ⇒ tz-naive. Anche il test `test_assign_regime_handles_duplicate_event_dates` aggiunto col Bug 1 fix usa dates tz-naive.

`_relabel_per_type_with_regime` non e' testato direttamente: i 172 test girano solo unit di `assign_regime` e e2e che usa `relabel` indirettamente — ma con eventi tz-naive (fixture sintetica), quindi il bug si manifesta SOLO sui dati reali dove `events["timestamp"]` e' UTC tz-aware.

Coerente con la lezione di Bug 1 (memoria `feedback_synthetic_fixtures_must_mirror_real_data_pathologies.md`): il fixture sintetico non rispecchia la patologia dei dati reali (tz-aware UTC).

## Fix proposto (agente 3 lo valuta)

Due punti di fix possibili, equivalenti:

**Opzione A — fix in `_relabel_per_type_with_regime`** (semplice, locale):
```python
center = cl["event"].get("center")
if center is None:
    continue
ts = pd.Timestamp(center)
if ts.tz is not None:
    ts = ts.tz_convert("UTC").tz_localize(None)   # normalizza a tz-naive prima di assign
lab = regimes.assign_regime([ts], regime_series)[0]
```

**Opzione B — fix difensivo in `regimes.assign_regime`** (piu robusto, copre futuri caller):
```python
def assign_regime(event_dates, regime_series):
    rs = regime_series.copy()
    rs.index = pd.to_datetime(rs.index).normalize()
    rs = rs.sort_index()
    rs = rs[~rs.index.duplicated(keep='last')]
    ev = pd.to_datetime(pd.Index(event_dates))
    if ev.tz is not None:
        ev = ev.tz_convert("UTC").tz_localize(None)   # difensivo: porta a tz-naive
    ev = ev.normalize()
    full_idx = rs.index.union(pd.Index(ev.unique()))
    full = rs.reindex(full_idx).ffill()
    return full.loc[ev].values
```

L'opzione B e' preferibile per coerenza col fix Bug 1 (gestire le patologie nel kernel, non in ogni caller). Lascia `assign_regime` come unica linea di responsabilita per la normalizzazione degli input.

## Presidio aggiuntivo richiesto

Aggiungere a `tests/test_regimes.py`:

1. `test_assign_regime_handles_tz_aware_event_dates` — riproduce esattamente:
   ```python
   ev = [pd.Timestamp('2013-07-31 18:00:00+00:00'),
         pd.Timestamp('2015-09-17 18:00:00+00:00'),
         pd.Timestamp('2020-03-15 21:00:00+00:00'),
         pd.Timestamp('2022-07-27 18:00:00+00:00')]
   ```
   Verifica che l'output sia **uguale** all'output sui corrispondenti tz-naive (`pd.Timestamp('2013-07-31')`, etc).

2. `test_relabel_per_type_with_regime_real_pattern` — fixture con cluster i cui `event.center` sono tz-aware UTC (`pd.Timestamp('...', tz='UTC')`); verifica che `_relabel` distribuisca a entrambi pos e neg con conteggi != 0 / != totale.

3. Aggiornare la fixture di `test_e2e.py` per usare `pd.Timestamp(..., tz='UTC')` su almeno un `event.center` (lezione gemella di Bug 1: fixture deve rispecchiare i dati reali).

## Stato dell'esecutore

- Codice congelato del package: NON toccato.
- Run autoritativo `result_authoritative.pkl`: T1/T3/T4/T5/T6/T8/T9/decomp/dedup/shared_control TUTTI VALIDI; solo `t7` invalidato dal Bug 2 (delta_p artefatto, va ignorato).
- Concordance E3.1 (`t7_concordance.json`): VALIDA, calcolata indipendentemente con `events["date"]` tz-naive ⇒ non transita per il path bacato.
- Driver dell'esecutore (`execute.py`): invariato; nessuna API consumata da T7 e' cambiata.

## Quando si riprende

Dopo che agente 3:
1. applica il fix (opzione B preferibile);
2. aggiunge i 2 (o 3) test sopra;
3. ri-lancia `pytest tests/ -q` → 174+/174+ verdi;
4. tu (Francesco) verifichi il diff prima del passaggio.

Allora l'esecutore: (i) ri-lancia smoke locale; (ii) ri-esegue **soltanto** la sezione T7 del driver (no full pipeline, perche T1/T3/T4/T5/T6/T8/T9 non sono affetti) e aggiorna `result_authoritative.pkl["t7"]` + sezione T7 di `REPORT_ESECUZIONE.md`. Tutti gli altri output (sha256 inclusi) restano stabili.

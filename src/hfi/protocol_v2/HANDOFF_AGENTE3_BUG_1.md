---
title: "Bug 1 (run reale): regimes.assign_regime esplode su event_dates con duplicati"
data: 2026-06-22
da: Esecutore
a: Agente 3
stato: ESECUZIONE REALE FERMATA al passo [5/8] assemble. Codice congelato NON modificato.
catena_di_custodia: agente 3 → esecutore (qui) → STOP → AGENTE 3 (per fix) → re-test → riprende l'esecutore
---

# Bug 1 — `regimes.assign_regime` non gestisce date duplicate

## Cosa e' successo

Eseguito `09_risultati/v2_signflip/execute.py` con calendario contaminanti completo (5151 centri unici). I passi [1/8]-[4/8] OK:

- events: 855 (events_with_regime_classifier.csv)
- prices: ES/TY/FGBL/STXE caricati, copertura 2010-01-03 → 2025-12-31 (STXE → 2025-10-03)
- regimi (window=63gg) calcolati: US 4909 giorni etichettati, EU 3932
- contaminanti dopo filtro `is_jobless_thursday` e match centri-evento: 4282 (effective reject pool)

Crash al [5/8] **`run.assemble`** → **`regimes.assign_regime`** (`regimes.py:76`):
```
ValueError: cannot reindex on an axis with duplicate labels
```

## Causa precisa

`assign_regime(event_dates, regime_series)` esegue:
```python
return full.reindex(ev).values
```
dove `ev = pd.to_datetime(pd.Index(event_dates)).normalize()`.

Su dati reali, `event_dates` contiene duplicati perche eventi distinti cadono nello stesso giorno solare:

- **86 date duplicate US** su 568 (esempi: FOMC decision 14:00 ET + FOMC press 14:30 ET ⇒ 2 record stessa `date`; quando CPI coincide con un FOMC ⇒ 3 record).
- **143 date duplicate EU** su 287 (ECB decision 13:45/14:15 CET + ECB press 14:30/14:45 CET ⇒ 2 record per ogni meeting).

`Series.reindex(idx)` da' ValueError se `idx` contiene duplicati. Comportamento documentato pandas, non un bug pandas — bug nel codice agente 3 che assume unicita.

## Perche il smoke (169/169) non l'ha catturato

`synthetic.dgp_structural_flip` + il fixture di `test_e2e.py` generano eventi su date **tutte diverse** (`pd.date_range("2019-01-01", periods=80, freq="MS")` + offset di 1 giorno per pos vs 15 per neg). Non c'e mai una collisione. Il presidio e2e di agente 3 e' valido per la completezza dell'output ma **non** per la robustezza ai pattern dei dati reali (decision+press stesso giorno, FOMC+CPI stesso giorno).

## Fix proposto (agente 3 lo valuta e implementa)

In `regimes.py`, `assign_regime`:

```python
def assign_regime(event_dates, regime_series: pd.Series):
    rs = regime_series.copy()
    rs.index = pd.to_datetime(rs.index).normalize()
    rs = rs.sort_index()
    rs = rs[~rs.index.duplicated(keep='last')]              # dedup serie regime per sicurezza
    ev = pd.to_datetime(pd.Index(event_dates)).normalize()
    full_idx = rs.index.union(pd.Index(ev.unique()))         # union UNIQUE per il ffill
    full = rs.reindex(full_idx).ffill()
    return full.loc[ev].values                               # .loc gestisce selector con duplicati
```

Vantaggi: (a) preserva la semantica as-of all'indietro (ffill su unione + lookup `.loc`); (b) ammette duplicati nel selector — propaga lo stesso regime a eventi della stessa data, che e' la semantica corretta (regime cambia per giorno, non per singolo annuncio); (c) deduplica anche la serie regime di input per sicurezza.

## Presidio aggiuntivo richiesto

Aggiungere a `tests/test_regimes.py` (o nuovo `tests/test_assign_regime_duplicates.py`):
- test che `assign_regime` su `event_dates` con duplicati ritorni un array della stessa lunghezza dell'input (non unique), con lo stesso valore per indici duplicati. Es. `event_dates = [d, d, d2]` ⇒ output di lunghezza 3.
- aggiornare il fixture `test_e2e.py` con almeno una data duplicata (es. decision+press) per esercitare il pattern reale.

## Stato dell'esecutore

- Codice congelato del package NON toccato.
- Driver `09_risultati/v2_signflip/execute.py`: invariato, gia compatibile col fix proposto.
- Output parziali del run interrotto: NIENTE (lo stop e' avvenuto prima dell'orchestratore — passo [5/8]).
- Calendario contaminanti `contaminants_v2_2026-06-22.csv`: stabile, 5151 centri, sha256 nel manifest.

## Quando si riprende

Dopo che agente 3:
1. corregge `assign_regime` (o equivalente);
2. aggiunge il test che esercita date duplicate;
3. ri-lancia `pytest tests/ -q` → tutti verdi (171+/171+);
4. tu (Francesco) verifichi il diff prima del passaggio.

Allora l'esecutore: (i) ri-lancia smoke locale, (ii) ri-esegue `09_risultati/v2_signflip/execute.py` con la stessa autorizzazione, (iii) consegna gli output grezzi.

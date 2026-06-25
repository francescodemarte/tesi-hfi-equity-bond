# Cancello descrittivo per il canale tassi

Diagnostica di indipendenza fra **regime equity-bond** e **intensità dello
shock di tasso** nelle finestre attorno agli annunci macro. **È un cancello,
non un modulo**: misura indipendenza, non stima il canale tassi.

## Confine del compito (vincolante)

- Verifica **descrittiva**. Nessuna stima di β̂_H del canale, nessuna risoluzione
  di sistemi strutturali.
- L'unica statistica ammessa è descrittiva e di qualità del dato: η² ANOVA,
  Cohen's κ (con allineamento label), conteggi di cella, momenti var/cov,
  vettori di cambiamento e loro angolo/rango.
- Niente fetch di dati. Input esterni datati. Seed dichiarato.
- Nessuno stub. Ogni funzione produce un calcolo dai dati o **solleva**.

## Stato

**38/38 test verdi** (osservato nel tool result). Niente esecuzione sui dati
reali — l'esecutore importa `gate.run_gate(events, event_moments, ...)` con
input congelati.

## Moduli

| File | Cosa fa |
|---|---|
| `config.py` | parametri congelati: finestra ±15 min, contratto default `FFc2`, soglie verdetto, seed master `20260622` |
| `rate_shock.py` | `rate_shock_intensity(prices, t_center)` = \|Δprice\| sulla finestra ±15 min; `build_event_intensity_table` per tabella eventi |
| `diagnostics.py` | 4 calcoli: `variance_decomposition` (η²), `cohens_kappa` (letterale), `partition_alignment_kappa` (label-free, max\|κ\| su permutazioni), `dichotomize`, `cell_counts`, `cells_below_threshold`, `change_vector`, `cosine_similarity`, `change_vectors_distinctness` |
| `gate.py` | `run_gate(events, event_moments)` → verdetto a/b/c/d sui numeri |
| `manifest.py` | provenance: contratto, finestra, seed, thresholds, hash input, timestamp esterno |

## Decisioni operative dichiarate

- **Contratto tasso:** default `FFc2` (densità piena dal Fronte 1; FFc1 ha
  gaps di roll-over). Alternative: `FFc3`, `FEIc1..c4`. Parametro esposto.
- **Finestra:** ±15 min, edge-bound 5 min mediane (stessa del protocollo v2).
- **Intensità:** \|post − pre\| (valore assoluto — il segno non interessa).
- **Tipi evento:** NFP, CPI, FOMC, ECB.
- **Soglia minima cella:** 30 (criterio (c)).
- **Soglie verdetto** (dichiarate, modificabili dall'esecutore):
  - η² ≤ 0.20 → (a) within-regime ampia
  - \|κ_aligned\| ≤ 0.20 → (b) dimensioni distinte (verdetto su overall;
    by-leg riportato ma non blocca per evitare bias campionario su n piccoli)
  - cosine angolo ≥ ⟨non-collineari su entrambe le fette⟩ → (d) terza
    equazione aggiunge informazione
- **Modalità partizione:** `median` (default) o `tertile_extremes`.

## Verdetto

`run_gate` produce `verdicts = {"a": bool, "b": bool, "c": bool, "d": bool}`.
Tutti i numeri (η², κ, conteggi, vettori, angoli) sono nel return.

**Niente giudizio di identificabilità complessiva** — quella è del ricercatore,
sulla base dei verdetti per criterio.

## Note al ricercatore (esplicite)

- La κ è calcolata con **allineamento label** (`partition_alignment_kappa`):
  la Cohen letterale dà 0 se i label set sono disgiunti (`{high,low}` vs
  `{positivo,negativo}`), che è il caso del prompt. L'aligned-κ misura
  accordo *strutturale* fra partizioni, indipendente dai nomi.
- Il by-leg dell'aligned-κ può avere bias positivo campionario su n piccoli
  (≈30 eventi/leg) per "ricerca della migliore permutazione" — è documentato
  in `gate.py` e non blocca il verdetto (b), che è valutato sull'overall.
- Il criterio (a) richiede η² basso **overall E per ogni tipo evento**
  (motivato dal prompt: "togliere il confounding col tipo di annuncio").
- Il criterio (d) richiede vettori non-collineari **su entrambe le fette**
  (regime positivo e regime negativo). Se le celle mancanti rendono il
  calcolo impossibile, verdetto (d) = `None` (status="missing_cells").

## Come si esegue

```bash
python3 -m pytest tests/ -q     # 38 passed
```

Esecuzione reale: NON in questo modulo. L'esecutore deve:
1. Caricare prezzi intraday del contratto tasso (default FFc2) come `pd.Series`.
2. Caricare gli eventi con `timestamp` (UTC), `leg`, `regime`.
3. Costruire la tabella intensità con `rate_shock.build_event_intensity_table`.
4. Costruire i momenti `event_moments[(regime, intensity_label)]` da `var_e`,
   `var_b`, `cov_eb` calcolati sulle finestre dell'annuncio.
5. Chiamare `gate.run_gate(events_with_intensity, event_moments)`.
6. Scrivere il manifest con `manifest.build_gate_manifest` e `write_manifest`.

## Buchi dichiarati (clausola del prompt)

Se un input manca, l'esecutore deve dichiararlo nel manifest (campo
`inputs[i].status="missing — non colmato"`) e riportare la diagnostica sul
sottoinsieme coperto, segnalando quanti eventi restano.

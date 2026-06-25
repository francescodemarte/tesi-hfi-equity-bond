# Spillover Fed → area euro — pipeline pre-registrata (terzo anello)

Traduzione in codice della spec `derivazione_test_spillover.md` (output del
secondo anello, derivazione dei test dal modello). Il modello è congelato, i
test sono derivati. **Questo modulo NON esegue sui dati reali**: l'esecuzione
è dell'anello successivo, dopo la review indipendente.

## Catena di custodia

modello (PDF) → **derivazione** (`derivazione_test_spillover.md`) →
**CODICE (questo package)** → review indipendente → esecutore sui dati reali.

## Stato

**60 test verdi.** Nessuna esecuzione sui dati reali. Nessun fetch di rete (il
modulo accetta dati come input passati dall'esterno).

## Struttura moduli

| Modulo | Stadio | Ruolo |
|---|---|---|
| `config.py` | – | parametri CONGELATI, seed dedicato `SPILLOVER_MASTER_SEED=20260622`, hash config |
| `surprises.py` | 0 | PC1 paniere tassi, separazione **JK per rotazione a restrizione di segno** (4 vincoli), poor man's, concordanza, guard ΔT5YIE |
| `calendar_clean.py` | 0.4 | filtri ufficiali (jobless Thursday, contaminanti ex-ante), mode `baseline` vs `robust_drop_fed_t1` |
| `responses.py` | 1 | Δy^B (bp), r^ES (log-return), Δsp (bp) close-to-close T+1 |
| `regression.py` | 2 | OLS + SE HC0/HC1/HC2/HC3 + bootstrap a coppie + p unilaterale |
| `tests_h.py` | 2 | T-H1 (primaria, p<0.05 NON corretto), T-H2/3/4 (BY q=0.10, m=3 fisso), gerarchia |
| `robustness.py` | 3 | Rigobon binario **subordinato**, poor-man's check, calendario, finestra |
| `report.py` | – | contratto di output: γ̂/δ̂/SE/t/p/BY + due letture (esistenza, attribuzione) + manifest |
| `run.py` | – | orchestratore `run_protocol_full(...)` su input passati; `main()` è BLOCCATO |

## Parametri congelati (`config.py`)

- Finestra sorpresa W^US: `[t − 10, t + 20]` min
- Paniere tassi US (PC1 → m_j): `FF_c1, FF_c2, ED_q2, ED_q3, ED_q4`
- Strumento equity (s_j): `ES` (E-mini S&P 500)
- Bootstrap: `B = 10_000`, seed dedicato `SPILLOVER_MASTER_SEED = 20260622`
- Molteplicità: H1 primaria `α = 0.05` (no correzione); famiglia secondaria `{H2, H3, H4}` con BY `q = 0.10`, `m = 3` FISSO
- Sorgenti **VIETATE come strumento**: `dT5YIE, T5YIE, breakeven, dBreakeven, T10YIE`

## Contratto di output (`report.py`)

Ogni asset porta una riga con: `gamma, delta, gamma_se, delta_se, t,
p_one_sided, side, by_decision, n, cov_type` + **due letture esplicite**:
- `reading_existence`: precedenza temporale + no-confondente (sempre).
- `reading_attribution`: condizionale alla separazione di segno (Ass. 2);
  l'attribuzione è il test di canale H4.

Il manifest finale ha: `config_version, config_hash, b_boot, seed (name+value),
n_events_{included,excluded}, timestamp` (timestamp PASSATO DALL'ESTERNO,
nessun clock interno per riproducibilità).

## Disciplina anti-fabbricazione

- Nessuna funzione restituisce valori costanti "verosimili" al posto di un
  calcolo. Ogni branch è un calcolo onesto o solleva (vedi i 17 `raise ...`).
- Nessun fetch di rete: i dati sono input esterni passati dal chiamante.
- Mai ΔT5YIE/breakeven come strumento (guardia in `surprises.validate_source`
  e in `surprises.separate_jk` indirettamente via PC1 sul paniere dichiarato).
- Seed dichiarato e riproducibile (`config.make_rng(name)` / `seed_for(name)`).
- Il manifest di ogni run ha `config_hash` (impronta SHA-256 dei parametri
  congelati): cifre prodotte sotto un config diverso si rifiutano.

## Come si esegue

```bash
# Solo unit + smoke su input sintetici (pre-review):
python3 -m pytest tests/ -q          # → 60 passed

# Esecuzione reale: NON è compito di questo modulo.
# L'esecutore importa run.run_protocol_full(m, s, responses, controls, ...)
# con dati congelati e manifest_timestamp passato dall'esterno.
```

`run.main()` è bloccato di proposito: solleva `SystemExit` se invocato.

## Cosa deve fornire l'esecutore

1. **Snapshot congelati** dei prezzi/yield intraday US (per W^US) e EU
   close-to-close T+1 (per le risposte). Niente è scaricato dal modulo.
2. **Calendario contaminanti** congelato con provenance: FRED (CPI, PPI,
   retail, GDP, PCE, durable, jobless), TreasuryDirect (aste major), Fed
   Board (testimonianze major); EU: Eurostat, BCE, fonti tedesche. Mode
   `baseline` (Fed in T+1 inclusa) e `robust_drop_fed_t1` (rimossa).
3. **Controlli minimali pre-dichiarati** (`x_j`): variazione overnight di un
   fattore globale di rischio + dummy di sotto-periodo, come colonne di
   `controls`. Niente oltre.
4. **`manifest_timestamp` ISO** al run, esterno al codice.

## Non in scope per questo anello

- Esecuzione sui dati reali.
- Fetch di dati esterni.
- Stima di numeri finali di risultato.
- Lettura/scrittura della tesi (livello editoriale).
- Aggiunta di nuovi test rispetto alla spec.

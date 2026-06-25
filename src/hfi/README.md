# src/hfi/ — Pacchetti tecnici

> 7 sotto-pacchetti, ciascuno installabile come modulo Python via
> `pip install -e .` dal root del repo. Suite di test totale: 462.

## Indice

| Sub-package | Ruolo | Test | Documento spec |
|---|---|---:|---|
| `protocol_v2/` | Protocollo v2 sign-flip (T1-T9, BY) | 175 | `protocol_v2/SPEC_codice_v2_signflip_2026-06-21.md` |
| `spillover_eu/` | Spillover Fed → euro area (H1-H4) | 68 | `spillover_eu/derivazione_test_spillover.md` |
| `rate_channel/` | Diagnostica canale tassi (term-structure + cancello doppio) | 45 | `rate_channel/README.md` |
| `strategy_excess/` | Strategia eccesso comovimento (training/test 2010-20 / 2021-25) | 51 | `strategy_excess/README.md` |
| `decomposition/` | Decomposizione canali (β_str con F-MOP + shrink) | 46 | `decomposition/README.md` |
| `third_channel/` | Terzo canale residuo (L, V, C; BY q=0.10 m=12) | 40 | `third_channel/README.md` |
| `event_driven/` | Strategie event-driven (CPI/NFP/FOMC + portafoglio) | 37 | `event_driven/README.md` |

## Importazione

Dopo `pip install -e .[dev]` dal root:

```python
from hfi import decomposition, event_driven, third_channel
```

Oppure entrando direttamente nella cartella del pacchetto:

```bash
cd src/hfi/decomposition
python3 -c "import cell_pipeline; print(cell_pipeline.__doc__)"
```

(Ciascun pacchetto usa import relativi locali al proprio `config.py`.)

## Convenzioni condivise

1. **Pre-registrazione**: tutti i parametri congelati in `config.py` con
   `config_hash()` (sha256 dello snapshot). Cambiare un parametro cambia
   l'hash, run tracciato come diverso.

2. **Seed dichiarato**: schema
   `np.random.SeedSequence([MASTER_SEED, blake2b(name)])`.
   Il valore intero è scritto nel manifest via `config.seed_for(name)`.
   - Master seed: 20260621 (protocol_v2 / rate_channel / decomposition /
     third_channel / event_driven), 20260622 (strategy_excess), 20260623
     (spillover_eu).

3. **Timestamp esterno**: passato all'invocazione, mai clock interno.

4. **Anti-fabbricazione**: 0 stub. Ogni branch fa un calcolo dai dati o
   solleva `ValueError`. Documentato negli `assert`/`raise` espliciti.

5. **Manifest di provenance**: ogni run scrive un JSON con `config_hash`,
   `seed.value`, sha256 di ogni input e di ogni modulo di codice eseguito.

6. **Test su DGP sintetici a verità nota**: oracoli analitici, NON ricalcoli
   della funzione testata.

7. **`main()` bloccato**: i `run_*.py` dei pacchetti tecnici sollevano se
   invocati direttamente. L'esecuzione sui dati reali è dell'esecutore
   (script in `results/0X_*/execute_*.py`).

## Esecuzione test

```bash
# Tutti i pacchetti
bash scripts/run_all_tests.sh

# Pacchetto singolo
cd src/hfi/decomposition && python3 -m pytest tests/ -v
```

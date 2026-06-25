# Architettura della catena di custodia

Pipeline modulare in 7 pacchetti pre-registrati, con disciplina anti-fabbricazione
e separazione dei ruoli (modello → derivazione test → coder → review → esecutore).

## I 7 pacchetti

```
┌─────────────────────────────────────────────────────────────────┐
│ 07_protocollo_v2_signflip                                       │
│ Test T1-T9: rilevanza, Lewbel, ampiezza, sign-flip BY+AR,       │
│ specificità NFP-vs-CPI, regimi esogeni, robustezze chiuse.      │
│ Output autoritativo: 4 celle robuste candidate.                 │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│ 12_decomposizione_canali                                        │
│ Doppio cancello: F-MOP + shrink-floor (a), banda di costruzione │
│ 12 punti = 4 code × 3 ρ (b). Verdetto per cella: robust /       │
│ fragile / not_identified.                                       │
│                                                                 │
│ INPUT: cluster del 07 (coerenza inter-pacchetto)                │
│ OUTPUT: 4 celle identified_robust (NFP/neg, CPI/neg, FOMC/neg,  │
│         CPI/pos a ±15 min); 6 channel_not_identified.           │
└────────┬──────────────────────────────────────────┬─────────────┘
         │                                          │
         ↓                                          ↓
┌──────────────────────────────────┐  ┌────────────────────────────────┐
│ 13_terzo_canale_residuo          │  │ 14_strategie_event_driven      │
│ Su ROBUST_CELLS del 12:          │  │ Su findings del 12:            │
│ test L, V, C come terzo canale   │  │ regola sign(equity)/sign(bond) │
│ residuo. BY q=0.10, m=12.        │  │ × size = |β_str|.              │
│                                  │  │ Sharpe ai 2 orizzonti.         │
│ Spec §3 rivista "antisymmetric"  │  │                                │
│ post-patologia §2/§3.            │  │ Strategia concentrata          │
│                                  │  │ pre-registrata (script extra): │
│ OUTPUT: 0/12 a q=0.10 pre-reg.   │  │ training 2010-18 / OOS 2019-25,│
│ (con varie sorprese e proxy).    │  │ filtri |surprise|≥p75, VIX≤p75 │
│                                  │  │ Portafoglio OOS Sharpe ≈ +1.4  │
└──────────────────────────────────┘  └────────────────────────────────┘

INDIPENDENTI:

┌────────────────────────────────────┐  ┌─────────────────────────────────┐
│ 08_spillover_fed_eu                │  │ 10_diagnostica_canale_tassi     │
│ H1: γ_y^Bund > 0 (primaria,        │  │ Diagnostica esistenza canale    │
│      non corretta).                │  │ tasso (cancello descrittivo).   │
│ H2-H4: BY q=0.10 m=3 fisso.        │  │ Term-structure PCA FEIc1..c4.   │
│ Robustezze pre-registrate.         │  │ Decomposizione DGP §7 oracoli.  │
└────────────────────────────────────┘  └─────────────────────────────────┘

┌────────────────────────────────────┐
│ 11_pratica_eccesso_comovimento     │
│ Strategia ε = (c-a)/σ²_pre.        │
│ Split training 2010-2020 / test    │
│ 2021-2025. Calibrazione strutturalm│
│ENTE train-only (raise on leakage). │
└────────────────────────────────────┘
```

## Disciplina condivisa

Ogni pacchetto rispetta queste invarianti:

1. **Pre-registrazione**: tutti i parametri congelati in `config.py` con
   `config_hash()` (sha256 dello snapshot). Cambiare un parametro cambia
   l'hash, run tracciato come diverso.

2. **Seed dichiarato**: schema `np.random.SeedSequence([MASTER_SEED, blake2b(name)])`.
   Il valore intero è scritto nel manifest via `config.seed_for(name)`.
   Master seed comuni: 20260621 (07/10/12/13/14), 20260622 (11), 20260623 (08).

3. **Timestamp esterno**: passato all'invocazione, mai clock interno.
   `run_protocol_full(..., manifest_timestamp="2026-06-22T15:00:00Z")`.

4. **Anti-fabbricazione**: 0 stub. Ogni branch fa un calcolo dai dati o
   solleva `ValueError`. Documentato negli `assert`/`raise` espliciti.

5. **Manifest di provenance**: ogni run scrive un JSON con `config_hash`,
   `seed.value`, sha256 di ogni input e di ogni modulo di codice eseguito.

6. **Test su DGP sintetici a verità nota**: ogni pacchetto ha una suite di
   unit-test che verifica oracoli analitici, NON ricalcoli della funzione
   testata. Tot. 462 test verdi nel repository.

7. **`main()` bloccato**: tutti i `run_*.py` dei pacchetti tecnici sollevano
   se invocati direttamente. L'esecuzione sui dati reali è dell'esecutore
   (script in `09_risultati/<pacchetto>/execute_*.py`).

## Catena di custodia inter-pacchetto

Il 12 riusa i **cluster del 07** (stesso MASTER_SEED=20260621, stesso
MOP_CV=23.1085, stesso BY_Q=0.10) per coerenza. Il 13 riusa le
**ROBUST_CELLS del 12**. Il 14 riusa i **β_str del 12** (illustrativi/PR) e
le **sorprese del 07** (req08, MP1 JK, m_e fallback). Cambiare i parametri
di un pacchetto upstream invalida i downstream — tracciato via config_hash.

## Esecuzione

Vedi `README.md` "Come riprodurre".

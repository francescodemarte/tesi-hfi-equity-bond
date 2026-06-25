# Diagnostica del residuo e terzo canale (spec terzo-canale-residuo v1)

Accerta se, dopo aver tolto canale di tasso (07/12) e identificato il canale
strutturale, il residuo equity-bond è rumore bianco o porta la traccia di un
**terzo canale comune** fra i tre candidati pre-registrati: liquidità (L),
volatilità (V), correlazione attesa (C). Solo su **celle robuste** (gate_a
PASS + pre-check PASS): FOMC/neg, NFP/neg, CPI/neg, CPI/pos.

## Stato

**38 passed, 1 xfailed** (osservato nel tool result). L'`xfail` è
**intenzionale** e documenta una patologia della spec §2/§3 (vedi §"Finding
da riportare al ricercatore" sotto).

## Moduli

| File | Ruolo |
|---|---|
| `config.py` | Candidati a priori (L/V/C) + segno atteso, 4 celle robuste, BY famiglia 12, soglie gate_a (4 valori MOP-Patnaik verificati a fonte) |
| `residual.py` | Costruzione ũ_e, ũ_b da netti + β_str (spec §2) |
| `proxies.py` | Ortogonalizzazione ΔZ⊥ via OLS residual (spec §4) |
| `tests_channel.py` | OLS HC/HAC: λ + p; comunalità con regola di segno (spec §5) |
| `multiplicity.py` | BY step-up su famiglia 12 con c(m)=Σ1/i (spec §6) |
| `sensitivity.py` | gate_a a 4 soglie (10/15/20%-bias + F>10) → strong/weak/fail |
| `whitening.py` | Autocorrelazione, dipendenza regime, cross-corr con ΔZ⊥ |
| `synthetic.py` | 4 DGP §9: third-channel / no-third / equity-only / Z-correlato-sorpresa |
| `pipeline.py` | Orchestratore per cella × candidato, BY su famiglia 12 |
| `manifest.py` | Provenance (pattern uniforme 07/08/11/12) |

## Soglie sensibilità gate_a (verificate alla fonte, spec §7)

| τ (worst-case bias) | cv MOP-Patnaik K=1 | sorgente |
|---|---|---|
| 10% | **23.1085** | `scipy.stats.ncx2.ppf(0.95, 1, 1/0.10)`, allineato al protocollo |
| 15% | **17.8662** | calcolato — la spec menziona "~19.7" a memoria; valore vero è 17.87 |
| 20% | **15.0616** | calcolato (coincide con stima ~15.1 della spec) |
| pratico F>10 | **10.0** | regola Staiger-Stock |

## ⚠️ Finding da riportare al ricercatore (patologia strutturale §2/§3)

**Sotto la definizione spec §2 dei residui** (ũ_e = r̃_e − β·r̃_b, ũ_b = r̃_b − r̃_e/β),
i carichi di Z sulle due regressioni sono **antisimmetrici per costruzione**:

```
coef(ũ_b, Z) = − coef(ũ_e, Z) / β        ∀ β > 0
```

Prova: detti r̃_e = γ_e·s + λ_e·Z + ε_e e r̃_b = γ_b·s + λ_b·Z + ε_b, allora
coef_e = (λ_e − β·λ_b), coef_b = (λ_b − λ_e/β), e β·coef_b = β·λ_b − λ_e = −coef_e.

**Conseguenza:** la regola di segno spec §3 è impossibile da soddisfare:
- L "concordant" (stesso segno): mai vero.
- V "both_negative": mai vero (servirebbe stesso segno).
- C "ambiguous": sempre vero (banale).

**Verifiche sperimentali (osservate nel tool result):**
- caso 1 (λ_e=+1.5, λ_b=+1.2 nel DGP): λ_e_obs=+0.297, λ_b_obs=−0.297 → segni opposti.
- caso 3 (λ_b=0 nel DGP): λ_e_obs=+1.53, λ_b_obs=−1.53 → comunalità True (entrambi
  significativi), sign discordant → terzo canale correttamente NON dichiarato per L.

**🚨 Conseguenza interpretativa (REVIEW #1, da non confondere).** Finché la spec
§2/§3 non è risolta, **L e V sono inascoltabili sui dati reali**: un futuro
verdetto "L `third_channel=False` su tutte e 4 le celle" **NON** è evidenza
empirica di non-canale — è la spec a renderlo impossibile da soddisfare.
Solo C (ambiguous) può tecnicamente passare, ma con valore informativo nullo
(la regola "ambiguous" è banalmente sempre True). Leggere "L/V negativi"
come reperto empirico è un errore di interpretazione del setup, non un fatto.

**Risoluzione = del ricercatore.** Due strade possibili:
1. Ridefinire ũ_b in modo non-antisimmetrico (es. ũ_b = residuo OLS di r̃_b su r̃_e,
   non sottrazione algebrica).
2. Mantenere §2 ma rivedere la sign rule §3 (es. "opposite-sign" per L, "both
   positive on coef_e" per V).

Il codice resta FEDELE alla spec — non patcha né le soglie né le aspettative.
Il test §9.1 (`test_dgp_case1_detects_third_channel_for_concordant_candidate`)
è marcato `xfail(strict=True)` con motivazione algebrica per rendere la
patologia VISIBILE.

## Anti-fabrication audit

- 0 stub `return <costante>`.
- 0 fetch di rete.
- 13 `raise` espliciti per input invalidi.
- Seed dichiarato + `seed_for(name)` esposto per manifest.
- Soglie cv calcolate alla fonte (spec §7), non a memoria.

## Cosa NON è qui

- Esecuzione sui dati reali.
- §6-bis (riestima a tre canali se Z identificato) — è del ricercatore dopo
  esito del test.
- Aggregazione cross-cell post-BY oltre la famiglia 12 — l'esecutore aggrega
  i 12 verdetti.

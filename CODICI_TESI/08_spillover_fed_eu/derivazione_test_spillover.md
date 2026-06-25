# Derivazione dei test — spillover Fed→area euro

Deliverable di derivazione (secondo anello della catena). Traduce le quattro Ipotesi del modello in test eseguibili, con stimatori, statistiche, soglie e robustezza. È scritto per l'anello successivo, che lo implementa come codice versionato con seed fissi; l'esecuzione sui dati reali resta separata e revisionata. Nessun numero è prodotto qui.

Convenzione di reporting, da agganciare a ogni stima e fissata una volta: γ̂ ha due letture, mai fuse. Come *esistenza* dell'effetto del Z^MP costruito poggia su precedenza temporale (verificabile) e no-confondente standard (assunto); come *attribuzione* a pura politica monetaria poggia in più sulla separazione di segno. I test di segno (H1–H3) sono claim di esistenza; il test di canale (H4) è il claim di attribuzione.

---

## Stadio 0 — Costruzione delle sorprese (input comune a tutti i test)

**0.1 Sorpresa grezza di tasso.** Per ogni annuncio FOMC j alla data t_j, nella finestra stretta W^US_j = [t_j − 10min, t_j + 20min]:
- m_j = primo componente principale delle variazioni di un paniere di strumenti di tasso a breve in W^US_j: Fed funds future mese corrente e successivo, eurodollar future a 2, 3, 4 trimestri.
- s_j = log-return del future E-mini S&P 500 in W^US_j.
- ΔT5YIE (e ogni breakeven) è BANDITO come strumento, qui come nel protocollo principale.

**0.2 Separazione monetario/informazione (Jarociński–Karadi).** Dal sistema bivariato (m_j, s_j) si ottengono le due serie ortogonali (Z^MP_j, Z^CBI_j) per rotazione a restrizione di segno:
- Cov(m, Z^MP) > 0, Cov(s, Z^MP) < 0 (restrizione: tasso su, azionario giù);
- Cov(m, Z^CBI) > 0, Cov(s, Z^CBI) > 0 (concordi).
- Convenzione: Z^MP_j > 0 = sorpresa restrittiva (hawkish).

**0.3 Riscontro poor man's.** In parallelo: Z^MP_j ≈ m_j · 1[m_j·s_j < 0]; Z^CBI_j ≈ m_j · 1[m_j·s_j > 0]. Test di concordanza: la correlazione di segno fra la costruzione per rotazione e la poor man's va calcolata e riportata; le divergenze sono dichiarate, non sanate. Questo riscontro è il presidio parziale sull'attribuzione (Ass. 2).

**0.4 Pulizia del calendario (snapshot congelato, ex-ante).** L'evento j entra nel campione solo se in [t_j, t_j+1] non cadono contaminanti datati. Fonti ufficiali, riproducibili, congelate con provenienza:
- US: FRED per i rilasci macro maggiori (CPI, PPI, retail, GDP, PCE, durable, jobless), TreasuryDirect per le aste maggiori (refunding, 10/30 anni), calendario Fed per le testimonianze programmate;
- EU: Eurostat (HICP flash, GDP area), calendario BCE (decisioni, discorsi maggiori), fonti tedesche (Ifo, ZEW, PMI).
- Comunicazione Fed in [t_j, t_j+1]: baseline = parte dello spillover (γ è l'effetto della stance comunicata), robustezza = rimozione degli eventi con intervento Fed maggiore in t_j+1 (Stadio 3).
- Output: manifest degli eventi inclusi/esclusi con ragione.

**Esito Stadio 0:** serie (Z^MP_j, Z^CBI_j), j = 1..J, con manifest. Atteso J dell'ordine di 100–150 lordi, meno dopo pulizia.

---

## Stadio 1 — Risposte dell'area euro a T+1

L'annuncio FOMC cade a mercati EU chiusi (≈ 20:00 CET), quindi la reazione si legge alla seduta t_j+1. Per ogni asset, baseline close-to-close attraverso t_j+1:
- Δy^B_j = variazione del rendimento del Bund 10Y, in p.b.
- r^ES_j = log-return dell'Euro Stoxx 50.
- Δsp_j = variazione dello spread BTP–Bund 10Y, in p.b.

Robustezza di finestra (Stadio 3): finestra intraday stretta attorno all'apertura EU di t_j+1.

---

## Stadio 2 — Regressione e test per ipotesi

Per ogni asset a ∈ {y^B, r^ES, sp}:

    Δa_j = α_a + γ_a · Z^MP_j + δ_a · Z^CBI_j + x_j' β_a + u_{a,j}

- Stima OLS; errori robusti all'eteroschedasticità (HC); se la spaziatura fra eventi lo richiede, HAC.
- x_j: controlli minimali pre-dichiarati (variazione overnight di un fattore globale di rischio; dummy di sotto-periodo). Niente oltre, per non sovra-controllare.
- Inferenza per bootstrap coerente col protocollo principale: B = 10.000, seed fisso dichiarato (master 20260621 o seed dedicato allo spillover, da fissare e scrivere nel manifest).

**T-H1 (primaria, esistenza, trasmissione di tasso).** H0: γ_yB ≤ 0 contro H1: γ_yB > 0. Test t unilaterale su γ_yB. Soglia piena p < 0,05 SENZA correzione di molteplicità (è la primaria). Esito nullo legittimo e pre-registrato.

**T-H2 (esistenza, canale azionario).** H0: γ_rES ≥ 0 contro H1: γ_rES < 0. Test t unilaterale su γ_rES. Famiglia secondaria (BY).

**T-H3 (esistenza, flight-to-quality interno).** H0: γ_sp ≤ 0 contro H1: γ_sp > 0. Test t unilaterale su γ_sp. Segno atteso ma non primario. Famiglia secondaria (BY).

**T-H4 (attribuzione, specificità del canale monetario).** Per gli asset in cui γ_a è significativo: confronto fra γ_a (canale MP puro) e δ_a (canale informativo). Si riporta (i) la significatività separata di γ_a e δ_a; (ii) una statistica sulla differenza, p.es. test di Wald su (γ_a − δ_a) o sul rapporto |γ_a|/|δ_a| con SE da bootstrap. Falsificazione dell'interpretazione come spillover di *politica* monetaria: un effetto che viva solo su δ_a (γ_a non distinguibile da zero mentre δ_a è significativo). Famiglia secondaria (BY). Questo è il test condizionale alla separazione di segno (Ass. 2).

**Molteplicità.** H1 primaria valutata a p < 0,05. Le tre {H2, H3, H4} formano la famiglia secondaria; controllo del false discovery rate con Benjamini–Yekutieli a q = 0,10, numerosità della famiglia fissa, in coerenza col protocollo principale.

---

## Stadio 3 — Robustezza

**3.1 Binario eteroschedastico (Rigobon 2003), subordinato.** Confronto di varianza e covarianza degli asset EU di T+1 fra giorni FOMC e giorni di controllo, come secondo identificatore che non usa la sorpresa puntuale. Dichiarato a credibilità minore: reintroduce un'assunzione di invarianza degli altri shock fra FOMC e controllo. Regola di lettura: se concorda con il primario corrobora; se diverge, prevale il primario (precedenza, verificabile). La gerarchia va scritta nel report, non trattata come parità.

**3.2 Riscontro di costruzione.** Concordanza in segno fra rotazione completa e poor man's (Stadio 0.3); divergenze dichiarate.

**3.3 Robustezza di calendario.** Rimozione degli eventi con intervento Fed maggiore in t_j+1; confronto di γ̂_a con il baseline. La differenza misura quanto pesa la comunicazione successiva.

**3.4 Robustezza di finestra.** Finestra intraday all'apertura EU di t_j+1 contro il close-to-close.

---

## Contratto di output del run

Per ciascun asset a e ciascuna ipotesi:
- γ̂_a, δ̂_a, SE (bootstrap), t, p unilaterale, esito BY;
- per H1, l'esito alla soglia piena; per {H2, H3, H4}, l'esito BY a q = 0,10.

Più: manifest degli eventi (inclusi/esclusi e ragione); seed e B dichiarati; provenienza dei dati; tabelle di robustezza (Rigobon, poor man's, calendario, finestra).

Ogni numero porta agganciata la lettura della gerarchia: γ̂ come esistenza (precedenza + no-confondente) e, separatamente, come attribuzione a pura MP (condizionale alla separazione di segno). L'esito nullo, su qualunque ipotesi, è riportato come tale e non forzato.

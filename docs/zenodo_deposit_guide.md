# Guida al deposit Zenodo

Procedura per pubblicare il dataset derivato + codice su Zenodo con DOI
permanente citabile nella bibliografia della tesi.

## Perché Zenodo

- **DOI permanente** citabile (es. `https://doi.org/10.5281/zenodo.XXXXXXX`)
- **Versionamento**: ogni release del repo GitHub può triggerare un nuovo DOI
- **Embargo opzionale**: puoi tenerlo private fino alla discussione, poi public
- **Integrazione GitHub**: clicco "Make release" su GitHub → Zenodo deposita automaticamente
- **Backup permanente**: CERN-grade storage, garanzia 20+ anni

## Setup (10 minuti)

### Step 1 — Account Zenodo
1. Vai su https://zenodo.org/
2. Login via GitHub (`Sign up with GitHub`) con account `francescodemarte`
3. Conferma email

### Step 2 — Collega ORCID (opzionale ma raccomandato)
1. Crea ORCID su https://orcid.org/register (gratuito, 5 min)
2. Su Zenodo: `Profile → ORCID iD → Connect`
3. Aggiorna `.zenodo.json` nel repo: campo `creators[0].orcid` con tuo ORCID

### Step 3 — Abilita integrazione GitHub
1. Su Zenodo: `Profile → GitHub`
2. Click `Sync now` per importare i tuoi repo
3. Trova `tesi-hfi-equity-bond` nella lista
4. **Flip the switch** a ON (verde)

### Step 4 — Crea la prima release GitHub
Da locale:

```bash
cd /home/francesco/TESI/repo-github-tesi
git tag -a v1.0.0 -m "v1.0.0: Initial release for thesis discussion

- 7 modular packages, 462 unit tests
- Authoritative run pickle pkg 07 (sha256 a9c13a7b...)
- 4 main findings documented in docs/results_summary.md
- Data manifest with sha256 expected values
- Setup scripts for FRED/Altavilla; Refinitiv intraday by user subscription"
git push origin v1.0.0
```

Poi su GitHub:
1. Vai su `https://github.com/francescodemarte/tesi-hfi-equity-bond/releases/new`
2. Tag: `v1.0.0`
3. Title: `v1.0.0 — Initial thesis discussion release`
4. Description: copia-incolla `docs/results_summary.md` o un riassunto breve
5. Click `Publish release`

Zenodo riceverà il webhook automaticamente e creerà il DOI in 2-5 minuti.

### Step 5 — Recupera il DOI
1. Su Zenodo: `Profile → Uploads` → vedrai il deposit di `tesi-hfi-equity-bond v1.0.0`
2. Click sul deposit → in cima vedi il DOI (es. `10.5281/zenodo.12345678`)
3. Aggiorna `CITATION.cff` nel repo con:
   ```yaml
   doi: 10.5281/zenodo.12345678
   ```
4. Aggiorna anche `README.md` con il badge:
   ```markdown
   [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.12345678.svg)](https://doi.org/10.5281/zenodo.12345678)
   ```
5. Commit e push:
   ```bash
   git add CITATION.cff README.md
   git commit -m "docs: add Zenodo DOI to citation"
   git push
   ```

### Step 6 — Visibilità (privato → public)
Il repo GitHub è ora **privato**. Quando vuoi pubblicare:

1. Settings → Change visibility → Public
2. Il DOI Zenodo è permanente; la visibilità Zenodo segue il repo

## Cosa scaricano i referee con il DOI

Cliccando il DOI dal CITATION.cff:
- ZIP di tutto il repository al tag v1.0.0
- File `.zenodo.json` con metadati strutturati
- Citation file per Mendeley, Zotero, EndNote, ecc.

Approssimativamente 7.8 MB di download.

## Costi
Zenodo è **completamente gratuito** (finanziato da CERN + UE).

## Alternative
- **figshare**: simile, ma meno academic-focused
- **Mendeley Data**: legato a Elsevier, comunque DOI permanente
- **Dataverse**: usato in scienze sociali, più complesso

**Raccomandazione**: Zenodo è lo standard de facto in fisica/data science academic ed è quello che la maggior parte dei referee si aspetta.

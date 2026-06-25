#!/bin/bash
# setup_data.sh — Scarica i dati esterni public per la pipeline
#
# Output: data_external/ popolato con FRED snapshots + Altavilla EA-MPD + JK.
# Tutto verificato via sha256 contro data_manifest.json.

set -e
cd "$(dirname "$0")/.."
mkdir -p data_external

echo "=== Setup dataset esterni public ==="

# 1) FRED daily series
for s in TEDRATE DGS2 DGS5 DGS10 DGS30 VIXCLS DFII5 T10YIE CPIAUCSL; do
    if [ ! -f "data_external/$s.csv" ]; then
        echo "  Scaricando $s da FRED..."
        curl -sS -o "data_external/$s.csv" \
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$s"
    fi
done

# 2) Altavilla EA-MPD — link academic-replication
# Il file completo è incluso nel repo (DATASET_TESI/01_eventi_hfi/EA-MPD_ECB_Altavilla2019.xlsx)
# Qui estraiamo i 3 fogli + i fattori TPQE
echo "  Estraendo fogli Altavilla EA-MPD..."
python3 scripts/extract_altavilla.py

# 3) Jarocinski-Karadi: il file è da scaricare manualmente da ECB website
# https://www.ecb.europa.eu/pub/research/working-papers/html/wp2030.en.html
# (replication package). Per ora marker:
if [ ! -f "data_external/jk_surprises_fomc.csv" ]; then
    echo "  ATTENZIONE: jk_surprises_fomc.csv NON scaricato automaticamente"
    echo "  Scaricare da: ECB replication package WP2030 (Jarocinski-Karadi 2020)"
    echo "  Salvare come data_external/jk_surprises_fomc.csv"
fi

# 4) Verifica sha256
echo ""
echo "=== Verifica integrita' sha256 ==="
python3 scripts/verify_data_integrity.py

echo ""
echo "Setup completato. Per i dati intraday Refinitiv vedere data_processed/.gitkeep"

#!/bin/bash
# run_all_tests.sh — Esegue le suite di test di tutti i pacchetti su DGP sintetici
set -e
cd "$(dirname "$0")/.."
TOTAL=0; FAILED=0

for pkg in 07_protocollo_v2_signflip 08_spillover_fed_eu 10_diagnostica_canale_tassi 11_pratica_eccesso_comovimento 12_decomposizione_canali 13_terzo_canale_residuo 14_strategie_event_driven; do
    echo ""
    echo "=== $pkg ==="
    cd "CODICI_TESI/$pkg"
    if python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3; then
        :
    else
        FAILED=$((FAILED+1))
    fi
    cd ../..
    TOTAL=$((TOTAL+1))
done

echo ""
echo "=== SUMMARY ==="
echo "  Pacchetti eseguiti: $TOTAL"
echo "  Suite con problemi: $FAILED"

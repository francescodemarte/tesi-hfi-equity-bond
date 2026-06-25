#!/bin/bash
# run_all_tests.sh — Esegue le suite di test di tutti i pacchetti su DGP sintetici
set -e
cd "$(dirname "$0")/.."
TOTAL=0; BROKEN=0

for pkg in protocol_v2 spillover_eu rate_channel strategy_excess decomposition third_channel event_driven; do
    echo ""
    echo "=== src/hfi/$pkg ==="
    cd "src/hfi/$pkg"
    if python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3; then
        :
    else
        BROKEN=$((BROKEN+1))
    fi
    cd ../../..
    TOTAL=$((TOTAL+1))
done

echo ""
echo "=== SUMMARY ==="
echo "  Pacchetti eseguiti: $TOTAL"
echo "  Suite con problemi: $BROKEN"

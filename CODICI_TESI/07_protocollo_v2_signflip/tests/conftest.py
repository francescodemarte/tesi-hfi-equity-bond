"""conftest pytest — mette la root del package sul sys.path.

I moduli del package si importano come top-level (`import config`,
`import provenance`, ...), coerente con lo stile dello script di analisi
esistente. Questo conftest inserisce la cartella del package (parent di
`tests/`) in sys.path così i test possono importarli.
"""
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

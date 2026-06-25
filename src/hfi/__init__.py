"""hfi — High-Frequency Identification of Equity-Bond Comovement.

Companion code package for the BSc thesis (Bocconi University 2026).

Subpackages:
  protocol_v2     — sign-flip protocol (T1-T9, BY q=0.10 m=3)
  spillover_eu    — Fed → euro area spillover (H1-H4)
  rate_channel    — rate-channel diagnostic with term-structure gates
  strategy_excess — excess comovement strategy (training/test 2010-20 / 2021-25)
  decomposition   — channel decomposition (β_str with F-MOP + shrink gates)
  third_channel   — residual third channel (L, V, C; BY q=0.10 m=12)
  event_driven    — event-driven strategies (CPI/NFP/FOMC + portfolio)
"""
__version__ = "1.0.0"
__author__ = "Francesco De Marte"
__license__ = "MIT"

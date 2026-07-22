"""Trading engine — the orchestration loop.

Owns the main async loop shared by live, testnet, and paper modes: on each
closed candle it asks the strategy for a signal, runs it through the risk
manager, executes approved orders, persists everything, and notifies.

STUB — implemented in the engine phase.
"""

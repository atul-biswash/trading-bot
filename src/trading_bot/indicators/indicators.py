"""Technical-indicator functions built directly on pandas / NumPy.

Indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ...) are implemented here
as small, pure, unit-tested functions rather than pulled from a third-party
library. This keeps a bot that can trade real money free of heavyweight,
fast-moving dependencies (e.g. numba/LLVM) and makes every calculation auditable.
Functions operate on and return pandas objects.

STUB — implemented in the indicators/strategy phase.
"""

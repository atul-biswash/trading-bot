"""ORM models for a relational store -- DEFERRED, and nothing is built here.

**This docstring promised something that is not being built.** It previously
described SQLAlchemy ORM models for signals, orders, trades and system events.
None of those exist, and none is being written; the promise is rewritten
rather than left standing, for the reason
:mod:`trading_bot.persistence.database` gives at length.

**What ships instead:** :mod:`trading_bot.persistence.store` holds its shapes
as frozen domain types and serialises them to JSON by hand. There is no
mapper, no metadata and no declarative base.

**The four entities named above are a WIDER scope than the store has, and the
difference is the point rather than an omission.** Signals, orders, trades and
system events are an AUDIT LOG -- a record of what happened, useful to a human
afterwards. The store holds only what the bot must know to behave correctly
after a restart, which is a strictly smaller set: the facts the venue cannot
answer. Everything else is reconstructed from the venue at boot, and a
persisted fact that goes stale is worse than an absent one.

**``core/interfaces.py`` already declares a ``Repository`` ABC for the audit
log -- ``save_signal``, ``save_order``, ``recent_signals`` -- with ZERO
implementations and ZERO callers (``M5h-043``).** The store deliberately does
not implement it: they answer different questions, and implementing a port by
accident because its name is nearby is how finding GG's two-milestone gap
opened. If the audit log is built, this is the file it would fill and that is
the port it would satisfy.
"""

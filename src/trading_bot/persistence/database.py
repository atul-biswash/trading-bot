"""A relational engine for this package -- DEFERRED, and nothing is built here.

**This docstring promised something that is not being built, and it is
rewritten rather than left.** It previously described an async SQLAlchemy
engine constructed from ``database.url``, SQLite first and Postgres by
changing the URL. That is a decision this project made and then did not act
on; leaving the promise standing would make this file the twelfth instance of
a ``src/`` docstring outliving its fact, a defect recorded eleven times
already (``M5f-029``, ``M5f-086``).

**What ships instead:** :mod:`trading_bot.persistence.store`, a concrete
JSON-file store holding only the facts the venue cannot answer. It is a file
and an ``os.replace``, not an engine and a session.

**THE DECIDING FACT, recorded because it is the part worth keeping.** The
store's write sits on the candle pipeline -- the pending-placement record is
written inside ``OrderExecutor.dispatch``, immediately before an irreversible
venue call -- and D1 forbids that pipeline being blocked by latency the code
does not bound itself. A file write is measurable and was measured: 41.562 ms
median including ``fsync`` on this repository's volume. A database engine's
connection, transaction and driver latency is bounded by nothing this tree
models. That is what decided it, not a preference about file formats.

**The relational design is DEFERRED, not rejected.** SQLite first, addressed
by a URL, with the same code targeting Postgres by changing that URL. If the
stored state ever outgrows a whole-file rewrite -- today it is two scalars
plus at most one pending record per enabled symbol, since ``dispatch`` refuses
while one is pending -- that is the design to return to, and this is the file
it would fill.

**It is recorded in THREE places besides this one, which is worth knowing
before any of them is deleted as dead.** ``config.yaml``'s ``database:``
block, ``DatabaseConfig`` in ``config/models.py``, and a fully written but
commented-out ``postgres:16-alpine`` service in ``docker-compose.yml`` with
its volume, credentials and a note to point ``database.url`` at it. A first
draft of this docstring claimed the intent lived nowhere else; that was FALSE
and was caught by grepping before it shipped. The reasoning above -- why a
file beat an engine -- is what is genuinely unique to this file.

**``DatabaseConfig`` and ``config.yaml``'s ``database:`` block still exist and
NOTHING READS THEM.** Measured: one grep hit in ``src/``, which is this
sentence's neighbour in the old docstring, and zero references in the entire
test suite. ``config.yaml`` ships ``url: sqlite:///data/trading_bot.db``
while ``requirements.txt`` declares neither SQLAlchemy nor any SQLite driver.
Whether to delete that config, comment it as unwired, or wire it is the
project owner's disposition and is deliberately not taken here -- deleting
config an operator may have edited is not a change to make in passing.
"""

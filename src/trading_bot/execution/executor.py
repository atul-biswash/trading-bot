"""Order executor.

**STUB. Nothing here is implemented, and nothing in ``src/`` places an order.**

What this file used to say described a seam and a target that no longer exist.
Both sentences are replaced rather than annotated, because ``src/`` describes
what the code does now.

**The seam is a ``RiskAssessment`` carrying an intent, not a signal.** Since
M5b the risk layer's output is
:class:`~trading_bot.core.assessment.RiskAssessment`, whose ``intent`` is an
approved, sized, protected :class:`~trading_bot.core.assessment.EntryIntent` or
:class:`~trading_bot.core.assessment.ExitIntent`. ``approved`` is the only
authoritative field on it.

**The target is not a single ``OrderRequest``.** Q-C section 2's four
configurations map to three outcomes, and ``OrderRequest`` covers one of them:
a stop with a take-profit becomes an OTOCO order list, a stop alone an OTO
order list, a take-profit alone is refused at config load, and neither enabled
is a single ``LIMIT``+``FOK``
:class:`~trading_bot.core.models.OrderRequest`.
:func:`~trading_bot.execution.placement.build_placement` already performs that
mapping, and has no caller.

**What is deliberately NOT stated here, because the milestone that writes this
module has not settled it.** Whether this module implements
:class:`~trading_bot.core.interfaces.OrderExecutor` is open -- that port takes
an ``OrderRequest``, which describes one of the three outcomes above. So is how
a dispatch sequence is funded from
:class:`~trading_bot.execution.dispatch_budget.DispatchBudget`, and so is what
happens when a placement's outcome cannot be determined. Describing any of them
here would commit the executor to a design nobody has chosen.
"""

"""Tests for ``Portfolio.close_position``'s two ways of valuing an exit.

Hermetic: no network, no real time, no patching beyond one deliberate
monkeypatch that forces an accrual to raise.

Exact ``Decimal`` assertions throughout. A result that is merely *close* is a
bug here in the strictest sense available: the whole subject of this module is
a rounding residual of the order of ``1E-24``, and a tolerant assertion cannot
see one at all.

**Fixtures are local rather than imported from ``test_risk_manager.py``.**
That module already exports ``long_position`` and ``test_modes.py`` already
imports from it -- the one place in ``tests/`` where two modules are coupled
that way, and a documented hazard, since an import-time break in the source
module fails every importer with a traceback naming the wrong file. A second
such coupling is not added here.

**And its helper could not serve anyway.** ``long_position`` sets
``entry_fill_price`` equal to ``entry_price`` by default and says so; more to
the point, its callers use ``quantity="2"`` against round exit values, and
``220 / 2`` divides evenly. MEASURED: that shape cannot express the
division mutation at all -- both paths return ``20``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_bot.core.enums import OrderSide, PositionSide, ProtectionState
from trading_bot.core.exceptions import FeeFillsIncompleteError, FeeUnresolvableError
from trading_bot.core.models import Fee, Position, Trade
from trading_bot.core.portfolio import Ledger, Portfolio, settle_exit

D = Decimal
SYMBOL = "BTCUSDT"
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
#: THE MEASURED FEE, not a stub: every SELL fill in the myTrades capture whose
#: SHA-256 is 111d1c15a3c5fff56148f172bfbcbec85baf5aabe2128f34fb622cafe5463970
#: carries commission "0.00000000" in USDT. Tests whose subject is not the fee
#: book with it; the fee's own tests use a fabricated non-zero amount.
USDT_ZERO_FEE = Fee(amount=D("0.00000000"), asset="USDT")

# --------------------------------------------------------------------------
# The awkward shape, MEASURED.
#
# `2450.12345678 / 0.02257` does not round-trip: multiplying the quotient back
# by the quantity returns `2450.123456780000000000000001`, a delta of `1E-24`.
# So this shape distinguishes the exact-total path from the division route on
# BOTH outputs -- the realised figure and the credit -- which is why it is the
# one used below.
#
# The entry price and the fill price are deliberately DIFFERENT, so a revert of
# `unrealized_pnl` to `entry_price` cannot pass either.
# --------------------------------------------------------------------------
AWKWARD_QTY = D("0.02257")
AWKWARD_ENTRY_REQUESTED = D("99000")
AWKWARD_ENTRY_FILL = D("100000")
AWKWARD_TOTAL = D("2450.12345678")
#: `total - entry_fill * quantity` = `2450.12345678 - 2257.00000`.
AWKWARD_PNL = D("193.12345678")


def _position(
    *,
    quantity: Decimal = AWKWARD_QTY,
    entry: Decimal = AWKWARD_ENTRY_REQUESTED,
    entry_fill: Decimal | None = AWKWARD_ENTRY_FILL,
    side: PositionSide = PositionSide.LONG,
) -> Position:
    """A position whose two entry prices differ, on the awkward quantity."""
    return Position(
        symbol=SYMBOL,
        side=side,
        quantity=quantity,
        entry_price=entry,
        entry_fill_price=entry_fill,
        entry_bar_time=NOW,
        protection=ProtectionState.UNKNOWN,
        opened_at=NOW,
        last_reconciled_at=NOW,
    )


class TestExactQuoteTotal:
    """The venue's own total, used as it arrived."""

    def test_the_exact_total_books_a_pnl_with_no_rounding_tail(self) -> None:
        """The point of the whole change.

        MUTATION: replace the ``exit_quote_total`` limb with the division
        route -- ``price = exit_quote_total / position.quantity`` followed by
        the legacy two lines. Both assertions below then read
        ``193.1234567800000000000000008`` and
        ``3450.123456780000000000000001``.
        """
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position()})

        pnl = portfolio.close_position(
            SYMBOL, exit_quote_total=AWKWARD_TOTAL, now=NOW, fee=USDT_ZERO_FEE
        )

        assert pnl == AWKWARD_PNL
        # The credit is the venue's figure verbatim: no multiplication of ours.
        assert portfolio.free_quote == D("1000") + AWKWARD_TOTAL
        assert portfolio.realised_today(NOW) == AWKWARD_PNL
        assert SYMBOL not in portfolio.positions

    def test_the_credit_is_the_total_verbatim_even_with_a_fee(self) -> None:
        """``fee`` nets off both outputs and nothing else changes.

        MUTATION: credit ``exit_quote_total`` without subtracting ``fee``, or
        subtract it twice.
        """
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position()})

        pnl = portfolio.close_position(
            SYMBOL, exit_quote_total=AWKWARD_TOTAL, now=NOW, fee=Fee(amount=D("0.5"), asset="USDT")
        )

        assert pnl == AWKWARD_PNL - D("0.5")
        assert portfolio.free_quote == D("1000") + AWKWARD_TOTAL - D("0.5")

    def test_a_short_is_the_mirror_of_a_long(self) -> None:
        """``_realised_from_total`` duplicates ``unrealized_pnl``'s side
        convention, so the SHORT limb is exercised rather than assumed.

        MUTATION: return ``gross - entry_cost`` for SHORT as well, or drop the
        SHORT branch so it falls through to ``Decimal(0)``.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={SYMBOL: _position(side=PositionSide.SHORT)},
        )

        pnl = portfolio.close_position(
            SYMBOL, exit_quote_total=AWKWARD_TOTAL, now=NOW, fee=USDT_ZERO_FEE
        )

        # entry_cost - gross, the exact negation of the long case.
        assert pnl == -AWKWARD_PNL

    def test_an_absent_entry_fill_price_refuses_rather_than_substituting(self) -> None:
        """The same fail-closed rule ``unrealized_pnl`` states, on the new path.

        MUTATION: fall back to ``position.entry_price`` when
        ``entry_fill_price`` is ``None``. That would book
        ``2450.12345678 - 99000 * 0.02257`` and write a permanent distortion.
        """
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position(entry_fill=None)})

        with pytest.raises(ValueError, match="cost basis is unknown"):
            portfolio.close_position(
                SYMBOL, exit_quote_total=AWKWARD_TOTAL, now=NOW, fee=USDT_ZERO_FEE
            )

        # Nothing was written: the refusal precedes every commit step.
        assert SYMBOL in portfolio.positions
        assert portfolio.free_quote == D("1000")
        assert portfolio.ledger is None


class TestPricePathIsUnchanged:
    """The legacy limb, preserved exactly.

    The strongest evidence for this is not in this file: the eight
    ``close_position`` tests in ``test_risk_manager.py`` are UNTOUCHED by this
    commit and still pass. These add local coverage of the same claim.
    """

    def test_the_price_path_still_computes_what_it_always_did(self) -> None:
        """MUTATION: rewrite the price limb as ``total - entry_fill * quantity``
        with ``total = quantity * exit_price``. Decimal distributivity fails, so
        that is a different expression and not merely a different spelling.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={SYMBOL: _position(quantity=D("2"), entry=D("100"), entry_fill=D("100"))},
        )

        pnl = portfolio.close_position(SYMBOL, exit_price=D("110"), now=NOW, fee=USDT_ZERO_FEE)

        assert pnl == D("20")  # (110 - 100) * 2
        assert portfolio.free_quote == D("1220")  # 1000 + 2 * 110
        assert portfolio.realised_today(NOW) == D("20")
        assert SYMBOL not in portfolio.positions

    def test_both_paths_agree_when_the_division_is_exact(self) -> None:
        """THE ANTI-DRIFT INSTRUMENT for the duplicated side convention.

        ``_realised_from_total`` restates ``unrealized_pnl``'s LONG/SHORT
        signs because it cannot call it. Where the division IS exact the two
        paths must agree exactly, so a change to either convention alone shows
        up here.

        The shape is chosen so ``220 / 2`` divides evenly -- this test is
        deliberately the one case that CANNOT distinguish the two
        implementations numerically, which is precisely what makes disagreement
        meaningful.

        MUTATION: flip the LONG and SHORT branches of
        ``_realised_from_total``.
        """

        def _fresh() -> Portfolio:
            return Portfolio(
                free_quote=D("1000"),
                positions={SYMBOL: _position(quantity=D("2"), entry=D("100"), entry_fill=D("100"))},
            )

        by_price = _fresh()
        by_total = _fresh()

        pnl_price = by_price.close_position(SYMBOL, exit_price=D("110"), now=NOW, fee=USDT_ZERO_FEE)
        pnl_total = by_total.close_position(
            SYMBOL, exit_quote_total=D("220"), now=NOW, fee=USDT_ZERO_FEE
        )

        assert pnl_price == pnl_total
        assert by_price.free_quote == by_total.free_quote
        assert by_price.ledger == by_total.ledger


class TestIllegalCombinations:
    """Refused, never resolved -- and refused before the absent-symbol return."""

    def test_both_given_is_refused(self) -> None:
        """MUTATION: prefer ``exit_quote_total`` and ignore ``exit_price``.
        That resolves silently and lets a caller believe the other was used.
        """
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position()})

        with pytest.raises(ValueError, match="never both"):
            portfolio.close_position(
                SYMBOL,
                exit_price=D("110"),
                exit_quote_total=AWKWARD_TOTAL,
                now=NOW,
                fee=USDT_ZERO_FEE,
            )

        assert SYMBOL in portfolio.positions
        assert portfolio.free_quote == D("1000")
        assert portfolio.ledger is None

    def test_neither_given_is_refused(self) -> None:
        """MUTATION: default ``exit_price`` to zero, or to the entry price.
        Either invents a number nobody supplied.
        """
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position()})

        with pytest.raises(ValueError, match="neither was given"):
            portfolio.close_position(SYMBOL, now=NOW, fee=USDT_ZERO_FEE)

        assert SYMBOL in portfolio.positions
        assert portfolio.free_quote == D("1000")
        assert portfolio.ledger is None

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"exit_price": D("110"), "exit_quote_total": D("220")}, "never both"),
            ({}, "neither was given"),
        ],
        ids=["both_given", "neither_given"],
    )
    def test_an_illegal_call_is_refused_even_for_a_symbol_not_held(
        self, kwargs: dict[str, Decimal], match: str
    ) -> None:
        """THE ORDERING CLAIM: the guards precede the absent-symbol return.

        An illegal call is a programming error whether or not the symbol is
        held. Checking after the early return would hide it on exactly the
        calls that hold no position -- silent on the very path a bug is most
        likely to take.

        MUTATION: move either guard below ``self.positions.get(symbol)``. Both
        rows then return ``Decimal(0)`` instead of raising.
        """
        portfolio = Portfolio(free_quote=D("1000"))  # holds nothing

        with pytest.raises(ValueError, match=match):
            portfolio.close_position(SYMBOL, now=NOW, fee=USDT_ZERO_FEE, **kwargs)


class TestOrderingSurvivesOnTheNewPath:
    """C12's discipline, re-checked through ``exit_quote_total``."""

    def test_a_raising_accrual_leaves_the_position_present_to_be_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The deletion is LAST, so a failed accrual is retryable.

        ``reconcile_open_positions`` iterates ``open_positions``, so a symbol
        removed from ``positions`` is never visited again. With the deletion
        last the same failure leaves the position present and the next pass can
        try again.

        MUTATION: move ``del self.positions[symbol]`` above
        ``record_realised_pnl``. The first assertion then fails.
        """
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position()})

        def _boom(self: Portfolio, amount: Decimal, *, now: datetime) -> None:
            self.ledger = Ledger(realised_pnl=Decimal("Infinity"), pnl_date=now.date())

        monkeypatch.setattr(Portfolio, "record_realised_pnl", _boom)

        with pytest.raises(ValidationError):
            portfolio.close_position(
                SYMBOL, exit_quote_total=AWKWARD_TOTAL, now=NOW, fee=USDT_ZERO_FEE
            )

        # THE POINT: the position survives, so a later pass can retry.
        assert SYMBOL in portfolio.positions
        assert portfolio.ledger is None  # ABSENT, not zero: nothing was booked
        # The credit DID land -- the accepted residual, documented on the
        # method rather than silently tolerated.
        assert portfolio.free_quote == D("1000") + AWKWARD_TOTAL

    def test_a_naive_now_is_rejected_before_anything_is_written(self) -> None:
        """MUTATION: move ``_require_aware`` below ``self.free_quote =
        proceeds``. The balance assertion then fails.
        """
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position()})

        with pytest.raises(ValueError, match="timezone-aware"):
            portfolio.close_position(
                SYMBOL,
                exit_quote_total=AWKWARD_TOTAL,
                now=NOW.replace(tzinfo=None),
                fee=USDT_ZERO_FEE,
            )

        assert SYMBOL in portfolio.positions
        assert portfolio.free_quote == D("1000")
        assert portfolio.ledger is None


# --------------------------------------------------------------------------
# The fee commit: a required Fee, and the ledger's settlement of an exit
# --------------------------------------------------------------------------
def _fill(
    trade_id: str,
    quantity: str,
    quote: str,
    *,
    order_id: str = "3189811",
    fee: Fee = USDT_ZERO_FEE,
    side: OrderSide = OrderSide.SELL,
) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol=SYMBOL,
        side=side,
        quantity=D(quantity),
        price=D("76577.74000000"),
        quote_quantity=D(quote),
        fee=fee,
        filled_at=datetime(2026, 9, 17, 9, 48, 2, 916000, tzinfo=timezone.utc),
    )


#: ORDER 3189811's TWO FILLS, VERBATIM from the myTrades capture whose SHA-256 is
#: 111d1c15a3c5fff56148f172bfbcbec85baf5aabe2128f34fb622cafe5463970. Their
#: quoteQty sums to 1772.00890360, which is the venue's own total on that
#: order's close_booked line in the log capture whose SHA-256 is
#: 0e6b673e16671152a4e08ca6cc8390e7b72ea8b75c3e7303fa0c16b4e04d223e.
FILLS_3189811 = (
    _fill("997264", "0.01945000", "1489.43704300"),
    _fill("997265", "0.00369000", "282.57186060"),
)


def test_settle_exit_aggregates_one_orders_fills() -> None:
    """Summed, never divided: fee, quote total, quantity, count and time.

    MUTATION: take the first fill, or book `Decimal(0)` for the fee. Every
    captured fee is zero, so the fee is pinned by its EXPONENT: a sum over
    `0.00000000` is `0E-8`, and `Decimal(0)` has exponent 0.
    """
    settlement = settle_exit(
        FILLS_3189811, order_id="3189811", quote_asset="USDT", executed_quantity=D("0.02314000")
    )

    assert settlement.quote_quantity == D("1772.00890360")
    assert settlement.quantity == D("0.02314000")
    assert settlement.fee.amount.as_tuple().exponent == -8
    assert settlement.fee.asset == "USDT"
    assert settlement.fill_count == 2
    assert settlement.filled_at == FILLS_3189811[1].filled_at


_BNB = Fee(amount=D("0.00001000"), asset="BNB")

#: FABRICATED rows: no captured SELL fill carries a non-USDT fee, so every
#: refusal below is constructed; the 128 BTC-denominated BUY fills in the
#: capture never reach an exit booking.
_SETTLE_REFUSALS = [
    ((), FeeFillsIncompleteError),
    ((_fill("1", "0.02314000", "1772.00890360", order_id="999"),), FeeFillsIncompleteError),
    (FILLS_3189811[:1], FeeFillsIncompleteError),
    ((_fill("1", "0.02314000", "1772.00890360", fee=_BNB),), FeeUnresolvableError),
    (
        (FILLS_3189811[0], _fill("997265", "0.00369000", "282.57186060", fee=_BNB)),
        FeeUnresolvableError,
    ),
    ((_fill("1", "0.02314000", "1772.00890360", side=OrderSide.BUY),), FeeUnresolvableError),
]


@pytest.mark.parametrize(
    ("trades", "expected"),
    _SETTLE_REFUSALS,
    ids=["no_fills", "another_order", "incomplete", "foreign_asset", "mixed_assets", "a_buy"],
)
def test_settle_exit_refuses_rather_than_guesses(
    trades: tuple[Trade, ...], expected: type[Exception]
) -> None:
    """Waiting can cure the first three and not the last three -- so the TYPE is pinned exactly.

    MUTATION: raise the base class for everything, or accept a partial list.
    M5i-115: an unmet `pytest.raises` raises `Failed`, not `AssertionError`.
    """
    with pytest.raises(FeeUnresolvableError) as excinfo:
        settle_exit(
            trades, order_id="3189811", quote_asset="USDT", executed_quantity=D("0.02314000")
        )

    assert type(excinfo.value) is expected


def test_close_position_refuses_a_fee_in_another_asset() -> None:
    """R-c: no converter. Refused BEFORE anything is written, held or not.

    FABRICATED fee in BTC. MUTATION: drop the guard, or place it after the
    absent-symbol return -- the unheld call below then returns `Decimal(0)`.
    """
    portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: _position()})
    btc_fee = Fee(amount=D("0.00000100"), asset="BTC")

    with pytest.raises(FeeUnresolvableError, match="fee in USDT"):
        portfolio.close_position(SYMBOL, exit_quote_total=AWKWARD_TOTAL, now=NOW, fee=btc_fee)
    with pytest.raises(FeeUnresolvableError, match="fee in USDT"):
        portfolio.close_position("ETHUSDT", exit_quote_total=AWKWARD_TOTAL, now=NOW, fee=btc_fee)

    assert SYMBOL in portfolio.positions
    assert portfolio.free_quote == D("1000")
    assert portfolio.ledger is None

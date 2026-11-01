from decimal import Decimal

import pytest

from parrilladas.modules.quotes.policies import can_send_quote


@pytest.mark.parametrize(
    ("total", "version", "approved_version", "already_sent", "expected"),
    [
        (None, 1, 1, False, False),
        (Decimal("100.00"), 1, None, False, False),
        (Decimal("100.00"), 2, 1, False, False),
        (Decimal("100.00"), 1, 1, True, False),
        (Decimal("-1.00"), 1, 1, False, False),
        (Decimal("NaN"), 1, 1, False, False),
        (Decimal("Infinity"), 1, 1, False, False),
        (Decimal("100.00"), 1, 1, False, True),
    ],
)
def test_quote_requires_price_and_current_approval(
    total, version, approved_version, already_sent, expected
):
    assert (
        can_send_quote(
            total=total,
            version=version,
            approved_version=approved_version,
            already_sent=already_sent,
        )
        is expected
    )

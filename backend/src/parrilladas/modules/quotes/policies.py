from decimal import Decimal


def can_send_quote(
    *, total: Decimal | None, version: int, approved_version: int | None, already_sent: bool
) -> bool:
    """Approval applies only to the reviewed version; a separate send action is required."""
    return (
        total is not None
        and total.is_finite()
        and total >= 0
        and version > 0
        and approved_version == version
        and not already_sent
    )

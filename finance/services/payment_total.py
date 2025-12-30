from decimal import Decimal
from django.db.models import Sum
from users.models import Payment


def recalculate_payment_total(payment: Payment) -> Decimal:
    """
    Recalculate and persist the total amount paid for a student's semester payment
    based on its component breakdowns.

    This is the single source of truth for Payment.amount_paid.
    """

    total_paid = (
        payment.breakdowns
        .aggregate(total=Sum("amount_paid"))
        .get("total")
    )

    # Normalize None → 0.00
    total_paid = total_paid if total_paid is not None else Decimal("0.00")

    # Persist the value
    payment.amount_paid = total_paid
    payment.save(update_fields=["amount_paid"])

    return total_paid

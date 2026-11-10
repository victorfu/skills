"""Checkout entry points."""
from pricing import split_cents


def split_bill(total_cents, people):
    """Return what each person pays, in cents."""
    if not isinstance(people, int) or people < 1:
        raise ValueError('people must be a positive integer')
    if total_cents < 0:
        raise ValueError('total_cents must not be negative')
    return split_cents(total_cents, people)

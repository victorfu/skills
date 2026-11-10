"""Money helpers. All amounts are integer cents."""


def split_cents(total_cents, parts):
    """Split total_cents into `parts` shares that add up to total_cents."""
    share, leftover = divmod(total_cents, parts)
    return [share + 1] * leftover + [share] * (parts - leftover)

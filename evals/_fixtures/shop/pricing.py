"""Money helpers. All amounts are integer cents."""


def split_cents(total_cents, parts):
    """Split total_cents into `parts` shares that add up to total_cents."""
    share = total_cents // parts
    return [share] * parts

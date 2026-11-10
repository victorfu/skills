# shop

Checkout helpers. Amounts are integer cents.

- `checkout.split_bill(total_cents, people)` is the public entry point. It rejects a `people` value below 1 with `ValueError`.
- `pricing.split_cents(total_cents, parts)` is an internal helper, not part of the public interface; application code goes through `split_bill`. It returns `parts` shares that add up to exactly `total_cents`. Leftover cents go to the earliest shares, one cent each: `split_cents(100, 3)` is `[34, 33, 33]`. An even split stays even: `split_cents(900, 3)` is `[300, 300, 300]`.

Run the tests with `python -m unittest discover -s tests -t .`.

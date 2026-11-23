# RFQ: asking the market makers

`--order rfq` asks Derive's or Paradex's market makers for a price instead of taking the
order book now. It is the owner's choice, never Butler's: use it only when they ask for it
("RFQ", "request a quote", "ask the market makers", "block price"). Rysk always quotes, so
it takes no `--order rfq`.

Makers quote a size worth their while, and may not quote a small order at all: say so
first for one, and offer the order book. A duty's order goes by RFQ the same way
(`duty.md`).

## The command

SKILL.md step 5's command, unchanged, with `--order rfq` added. Keep the same total bound
from this turn's quote; never add `--min-price` or `--max-price` (those are resting orders):

| Trade | Bound (from the quote) | Add |
| --- | --- | --- |
| Open (sell a put) | `--min-premium`, `--max-collateral` | `--order rfq` |
| Buy | `--max-cost` | `--order rfq` |
| Sell back | `--min-proceeds` | `--order rfq` |
| Buy back | `--max-cost` | `--order rfq` |

## Before they approve: one line, in their words

Once approved, it asks the makers for up to 20 seconds and takes the best quote inside their
limit, fees included. If none fits, nothing trades and nothing is spent. On Derive a maker's
quote the order book beats is refused, and the next maker's is tried; an RFQ never falls back
to the book.

## After

- **Filled**: report it as any fill; the outcome says "Order: RFQ".
- **"no maker quoted inside the approved bound"**: nothing traded. Give the best quote it
  names. Never file again at a looser bound without their yes; the order book (the same
  command without `--order rfq`) is the other offer.
- **"takes no rfq orders here"**: RFQ is off for that venue; offer the order book.
- **Paradex**: a size off its RFQ size step, or an option whose every maker quote sits
  outside Paradex's price band (usually a cheap one far from the money), cannot trade by
  RFQ; offer the order book.

## Say to the owner

"I'll ask Derive's market makers for a price on 0.1 ETH of the $1,850 call, 27 November,
for at most $8 all in. Once you approve, they have 20 seconds to quote; the best quote under
$8 is taken, and if none is, nothing is bought. You can lose all of it. Yes?"

No fill: "No maker quoted under your $8 within 20 seconds, so nothing was bought. The best
was $8.40. I can ask again at a higher limit if you say so, or buy from the order book."

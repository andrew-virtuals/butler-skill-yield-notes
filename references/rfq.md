# RFQ: asking the market makers

`--order rfq` asks Derive's or Paradex's market makers for a price instead of taking the
order book now. It is the owner's choice, never Butler's: file it only on their word
("RFQ", "request a quote", "ask the market makers", "block price", or their pick of it
when Butler offers it below). Rysk always quotes, so it takes no `--order rfq`.

Makers quote a size worth their while, and may not quote a small order at all: say so
first for one, and offer the order book. A duty's order goes by RFQ the same way
(`duty.md`).

## When Butler brings it up

An owner may not know RFQ exists. On Derive or Paradex, Butler offers it beside the order
book, in one line and once per trade, in these three cases and no other:

| When | How it shows |
| --- | --- |
| The order is bigger than the book's best price holds | the quote carries `rfq_offer` |
| The book's price is poor (a wide market) | the quote carries `rfq_offer` |
| A book order did not fill | SKILL.md § Failure handling, "No fill": with the re-quote |

- **`rfq_offer` is said as written**, as the last line of the reply that offers the
  trade, after the quote's warnings and safeguards. The helper decides when: never add
  it to a quote that has none, and it has none for the smallest order (`min_size`).
- **It is an offer, never a switch.** The owner picks the book or RFQ, and no answer
  means the book.
- **A safeguard still needs its yes.** Picking RFQ for a held trade is that yes: quote
  again with `--waive`, and file with `--waive <waive>` and `--order rfq`.
- **Never for an empty book.** A quote that says `no live ask` or `no live bid` is not a
  reason to bring up RFQ: follow SKILL.md § Failure handling. On Paradex, when the owner
  asks for RFQ on a stock, index or commodity option whose quote says that, there is no
  quote to take the bound from, so nothing can be filed: say so, and never make up a
  bound.

After a no-fill, in their words: "Nobody took it at your $8 limit, so nothing was bought.
I can quote it again for the order book, or ask the market makers for a price instead
(RFQ): they get 20 seconds to quote inside your limit, and if none does, nothing is
bought. Which one?"

## Asked for the RFQ price before filing

The makers are asked only after the owner approves, so no quote before that is theirs.
Asked for one ("get me an RFQ quote", "just show me the quotes"), quote as usual and say
the figure is the order book's: "That is today's order-book price, about $2.47. The
market makers' price comes after you approve, never above your $2.60 limit; if none
quotes inside it, nothing is bought." Never call the book's price an RFQ quote.

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

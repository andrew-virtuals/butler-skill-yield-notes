# Buying a call or a put

Buying an option is **not yield**. The owner pays a price up front - the premium plus
Derive's fee - and gets the right to a payout at expiry:

- a **call** pays (settlement price - strike) x size if the asset ends **above** the
  strike: upside on a rise, without buying the asset;
- a **put** pays (strike - settlement price) x size if it ends **below** the strike: a
  bet on a fall, or a hedge for an asset they already hold.

If the asset does not end past the strike, the option expires worthless and the whole
cost is gone. That cost is also the most they can lose: nothing is borrowed and
nothing is locked beyond it.

## The first-time check

Before an owner's first bought option ever, get three plain yes answers. If any is no
or vague, do not quote:

- "You can lose everything you pay for this. Clear?"
- "It only makes money if ETH ends past the breakeven on the expiry date, and it is
  worth a little less every day ETH stands still. Clear?"
- "You can sell it back before then, but only for what the market pays at the time,
  often less than you paid. Clear?"

And before every buy, an explicit yes to the number: "You can lose the whole
$199.54 - yes?" A yes to the idea is not a yes to the amount. The figure goes in the
question itself, card or text; "the entire amount spent is gone" is not a number.

## Choosing is theirs

Butler never picks the trade. "Just buy whatever looks good", "you pick", "the best
one": say Butler does not choose trades, and ask which asset, the most they will
spend, and roughly when it should expire. Quote nothing until they have named an
asset and an amount. Never make up a budget, even a small one.

The helper's strike rule is a starting point, said as one, with the quote's own
numbers: "That is a call about 5% above today's price, expiring 30 October. Nearer,
further, or another date?" `--delta 0.3` instead of `--otm-pct` holds the odds steady
if they ask for that.

## Saying it out loud

Every number is a **field on the buy quote**. Never compute one.

| In the sentence | Field |
| --- | --- |
| the most they pay, and the most they can lose | `max_cost_usd` (the card's "You pay at most") |
| what it costs at today's price | `total_cost_usd` (`premium_usd` + `fee_usd`) |
| fees | `fee_usd`, its own line |
| where it starts paying at expiry | `breakeven` |
| the price it turns on | `strike` |
| the date | `expiry` (08:00 UTC) |
| how much | `size`, in units of the asset |
| how good the price is | `overpay_vs_fair_vol_pts` |

## The shape

Four beats, in this order:

1. **It is a bet, and the most it can lose.** "This is not yield. You pay at most
   $199.54, and you can lose all of it."
2. **What it pays.** "If ETH is above $2,600 on 30 October, the call pays $2.95 for
   every dollar above that."
3. **Breakeven and time, in one sentence.** "It only beats what you paid above about
   $2,664, and each day ETH stands still it is worth a little less."
4. **The date.** "It settles on 30 October at 08:00 UTC; you can sell it back before
   then."

For a put, the same with "below": "If ETH is below $2,350 on 30 October, the put pays
$3.45 for every dollar below that; it only beats its cost below about $2,295."

## Words

| Do not say | Say |
| --- | --- |
| "invest", "yield", "earn" | "pay $190 for the chance of a payout" |
| "protected", "insured", "safe" | "if ETH ends below $2,350, the put pays the difference in USDC" |
| "you can't lose more than…" as comfort | "you can lose all $199.54" |
| "it will pay if ETH goes up" | "it pays if ETH is above $2,664 on 30 October" |
| "cheap" | the price, and `overpay_vs_fair_vol_pts` if it is wide |

## When the price is poor

`overpay_vs_fair_vol_pts` is how far over Derive's own mark the ask sits: what the
buyer gives away crossing the spread.

- over 3: say the market is wide today and they are paying above fair value.
- over 5: the helper refuses, with "you would be paying N% over fair value".

## A hedge

A put on an asset they hold limits the loss on it below the strike, for a price.
Quote it with `--size` set to what they hold (never more - beyond that it is a bet on
a fall, not a hedge). Say what it does not do: it pays USDC into the Derive account at
expiry; it does not sell their ETH, and between the strike and spot they still carry
the fall.

## Closing early

An option the owner **bought** shows in `acp options account` positions with a
positive `size`; a sold note shows negative, and closing that one is a buy-back
(`references/selling.md`).

**The size is theirs, up to what they hold.** Read `positions` first. Asked to close
more than the position ("sell 5 of my ETH calls" with 0.16 held), say so and ask:
"You hold 0.16 of that call, not 5. Sell all 0.16?" Never shrink the size quietly,
and never pick between two positions for them.

Quote the close with `quote --side close --instrument <name> --size <size>`. Say
`net_proceeds_usd` against what they paid (the lifecycle duty's `PREMIUM_USD`), plainly
when it is less: "Selling back now gets about $178.73 after fees, against $190.03 you
paid." Give any `warnings` as written ("fees take 16% of what the bid pays").

**Then ask for the floor**, the least they will take, with `min_proceeds_usd` as the
suggestion: "The least you'd take? I'd suggest $169.79, so a small move doesn't stop
it." File only the floor they agreed, and quote again after their answer: the card
needs a quote under 60 seconds old.

If it does not fill, nobody bought at that floor; the price moved. Say exactly that,
never "no liquidity", and re-quote before offering again, never re-filing the same
floor. With `no live bid`, nobody is bidding for this option right now: holding it to
expiry costs nothing, and the lifecycle duty reports the outcome.

A close sells only what they hold (`reduce_only` on the venue). After a confirmed
close, the lifecycle duty for that instrument is deleted; if part is still held, it is
filed again for what remains.

## At expiry

Derive settles in cash at 08:00 UTC on the expiry date. A bought option that ends in
the money pays automatically into the Derive account: (settle - strike) x size for a
call, (strike - settle) x size for a put. Nothing has to be done to collect it. It
stays in the account until withdrawn. One that ends out of the money pays nothing.

The `options-lifecycle@8` duty, filed after a confirmed buy, tells the owner the day
before and again with the outcome. It is filed with:

| Param | From |
| --- | --- |
| `INSTRUMENT` | `approvalOutcome.instrument` |
| `PRODUCT` | `long_call` or `long_put` |
| `UNDERLYING` | the instrument's prefix |
| `STRIKE` | `approvalOutcome.strike` |
| `SIZE` | `approvalOutcome.filledSize` (a fill can be partial) |
| `PREMIUM_USD` | `approvalOutcome.totalCostUsd` |
| `COLLATERAL_USD` | 0 |

No `DELIVER_ASSET`: a bought option pays cash and buys nothing.

## Say to the owner

"This is a bet, not yield. You pay at most **$199.54** for 2.95 ETH calls at $2,600;
if ETH is not above about $2,664 on 30 October you lose all of it, and it is worth a
little less each day ETH stands still. You can lose the whole $199.54 - yes?"

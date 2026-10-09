# Saying a note out loud

Every number below is a **field on the quote object**. Nothing here is computed by
the model. If a sentence needs a number the quote does not carry, the sentence is
wrong.

| In the sentence | Field |
| --- | --- |
| what they earn | `net_premium_usd` (never `premium_usd` - that is before fees) |
| the floor on the open | `min_premium_usd` |
| "a year, if you kept rolling" | `apr_pct` |
| the price they might buy or sell at | `strike` |
| the date | `expiry` |
| how much of the asset | `size` |
| what is locked | `collateral.amount` (`collateral.usd` in dollars) |
| fees | `fee_usd` |
| how good the price is | `edge_vs_fair_vol_pts` |

## The shape

Four beats, in this order. The third is not optional and does not get softer
language than the second.

1. **The money, and the date.** "Your $4,991 can earn $56 over the next 23 days."
2. **The good case.** "If ETH is above $2,300 on 30 October, you keep both."
3. **The bad case, in the same breath and the same register.** "If it is below, you
   pay $2,300 each for 2.17 ETH - and if ETH is at $2,000 by then, that is about $650
   more than they are worth, which the $56 does not cover."
4. **What is locked.** "Your $4,991 cannot be touched until 30 October."

## Words

| Do not say | Say |
| --- | --- |
| "yield", "APY", "earning 16%" | "earns $56 over 23 days - about 18% a year if you kept doing it" |
| "if assigned" | "you pay $2,300 for each ETH" |
| "risk of loss" | "if ETH is at $2,000 you are down about $650" |
| "capital is deployed" | "your $4,991 is locked until 30 October" |
| "collect premium" | "the $56 is yours once it fills, whatever happens" |
| "safe", "guaranteed", "low risk" | nothing - do not reach for a reassurance |

The premium is the only guaranteed part. Say *that* is certain, and be plain that
nothing else is.

## APR, honestly

`apr_pct` annualises one note that has not happened yet. It is not a rate of return
and it does not repeat by itself - it assumes they roll into a similar note every
month at a similar price, which the market may not offer.

Always attach the condition: "about 18% a year **if you kept rolling it at today's
prices**". Never "18% APY", and never put it in a headline on its own.

## When the price is poor

`edge_vs_fair_vol_pts` is how far below Derive's own mark the bid sits. It is
negative for a seller - that is the spread, and it is what a market maker keeps.

- worse than -3: say the market is wide today and they are not getting a great
  price.
- worse than -5: the helper refuses. Say nothing is worth doing and why.

An owner who hears "18% a year" without hearing that the spread took part of the
premium has been told half of it.

## The wheel

After a put is assigned, the classic next note is a covered call on the asset. Not
here yet: v1 offers puts only, Derive settles in cash, and a call needs the asset
inside the Derive account. The next note is another put. Offer it as a choice, not a
sequence: an owner who has just taken a loss may want to stop.

Never auto-roll without a fresh yes.

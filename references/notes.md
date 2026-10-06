# Saying a note out loud

Every number below is a **field on the quote object**. Nothing here is computed by
the model. If a sentence needs a number the quote does not carry, the sentence is
wrong.

| In the sentence | Field |
| --- | --- |
| what they earn | `net_premium_usd` (never `premium_usd` - that is before fees) |
| "a year, if you kept rolling" | `apr_pct` |
| the price they might buy or sell at | `strike` |
| the date | `expiry` |
| how much of the asset | `size` |
| what is locked | `collateral.amount` |
| fees | `fee_usd` |
| how good the price is | `edge_vs_fair_vol_pts` |

## The shape

Four beats, in this order. The third is not optional and does not get softer
language than the second.

1. **The money, and the date.** "Your $5,000 can earn $54 over the next 24 days."
2. **The good case.** "If ETH is above $2,450 on 30 October, you keep both."
3. **The bad case, in the same breath and the same register.** "If it is below, you
   have bought 2.04 ETH at $2,450 - and if ETH is at $2,200 by then, that is a $400
   loss the $54 does not cover."
4. **What is locked.** "Your $5,000 cannot be touched until 30 October."

## Words

| Do not say | Say |
| --- | --- |
| "yield", "APY", "earning 16%" | "earns $54 over 24 days - about 16% a year if you kept doing it" |
| "if assigned" | "you have bought ETH at $2,450" |
| "risk of loss" | "if ETH is at $2,200 you are down about $400" |
| "capital is deployed" | "your $5,000 is locked until 30 October" |
| "collect premium" | "the $54 is yours today, whatever happens" |
| "safe", "guaranteed", "low risk" | nothing - do not reach for a reassurance |

The premium is the only guaranteed part. Say *that* is certain, and be plain that
nothing else is.

## APR, honestly

`apr_pct` annualises one note that has not happened yet. It is not a rate of return
and it does not repeat by itself - it assumes they roll into a similar note every
month at a similar price, which the market may not offer.

Always attach the condition: "about 16% a year **if you kept rolling it at today's
prices**". Never "16% APY", and never put it in a headline on its own.

## When the price is poor

`edge_vs_fair_vol_pts` is how far below Derive's own mark the bid sits. It is
negative for a seller - that is the spread, and it is what a market maker keeps.

- worse than -3: say the market is wide today and they are not getting a great
  price.
- worse than -5: the helper refuses. Say nothing is worth doing and why.

An owner who hears "16% a year" without hearing "and you are handing over a quarter
of the premium to get filled" has been told half of it.

## The wheel

After a put is assigned, the covered call on the same asset is the natural next
note. Offer it as a choice, not a sequence: an owner who has just bought ETH at a
loss may want to keep the ETH rather than agree to sell it again.

Never auto-roll without a fresh yes.

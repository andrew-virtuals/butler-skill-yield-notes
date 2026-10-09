# Selling a put for income

A note is one **cash-secured put**, sold short and **fully collateralised** in USDC
(strike x size): the owner agrees to buy the asset at a lower price if it falls
there, and keeps the premium either way.

This is not lending and not a vault. The owner is **selling someone else insurance**
and keeping the fee. The premium is certain. What they own at expiry is not.

## Does it fit?

- **Would they buy the dip?** A note fits idle USDC whose owner would happily buy the
  asset lower. If not - or they want to earn on an asset they hold - there is no note
  here: say so and stop.
- **How much, in one asset.** The collateral is locked until expiry. Getting out
  early means buying the note back, which can cost more than it brought in.

## The first-time check

Before an owner's first note ever, get three plain yes answers. If any is no or
vague, do not quote:

- "If ETH falls hard, you end up paying the strike for it, at a loss. Clear?"
- "Your money is locked until the expiry date. Getting out early means buying the
  note back, and that can cost more than you were paid. Clear?"
- "The premium is yours whatever happens. The collateral is not. Clear?"

## Saying a note out loud

Every number below is a **field on the sell quote**. Nothing here is computed by the
model. If a sentence needs a number the quote does not carry, the sentence is wrong.

| In the sentence | Field |
| --- | --- |
| what they earn | `net_premium_usd` (never `premium_usd` - that is before fees) |
| the floor on the open | `min_premium_usd` |
| "a year, if you kept rolling" | `apr_pct` |
| the price they might buy at | `strike` |
| the date | `expiry` |
| how much of the asset | `size` |
| what is locked | `collateral.amount` (`collateral.usd` in dollars) |
| fees | `fee_usd`, always its own line |
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

Then the separate ownership question, in the asset's terms: "Happy to own 2.17 ETH at
$2,300 on 30 October?" A yes to the yield is not a yes to this.

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

## Settlement and delivery

**Derive settles in cash.** An in-the-money put reduces USDC by (strike - settlement
price) x size; it does not deliver ETH. "You now own ETH at $2,300" is true only after
a separate spot buy has filled. The lifecycle duty does that buy only when it is filed
with `DELIVER_ASSET` on, which is only when the owner asked for it before the open.

The premium and the freed collateral stay in the Derive account until withdrawn.

## Buying back early

A sold note shows in `acp options account` positions with a **negative** `size`.
Buying it back ends it before expiry and frees its collateral. Quote it with
`quote --side buyback --instrument <name> --size <size as a positive number>
--premium-received <USD>`, where the premium is the open's `netPremiumUsd` (or the
duty's `PREMIUM_USD`) scaled to the size being bought back.

Say `total_cost_usd`, then `result_usd`, plainly when it is negative: "Buying it back
now costs about $4.46 with fees. You were paid $3.00 for it, so you would take a $1.46
loss now." Give any `warnings` as written. Then say what waiting does: holding to
expiry costs nothing to do, and the note may still expire worthless. The ceiling is
theirs to agree: `max_cost_usd` unless they name one; never raise it without asking.

The usual reasons: most of the premium is already earned and they want the collateral
back, the asset is falling toward the strike and they would rather pay than buy it
there, or they need the USDC. Buying back after a sharp fall usually locks in a loss
that expiry might not have; say so, and let them choose.

## The wheel

After a put is assigned, the classic next note is a covered call on the asset. Not
here yet: v1 offers puts only, Derive settles in cash, and a call needs the asset
inside the Derive account. The next note is another put. Offer it as a choice, not a
sequence: an owner who has just taken a loss may want to stop.

Never auto-roll without a fresh yes.

## Sizes

The smallest note is Derive's minimum size x the strike: about $230 on ETH at
today's strikes, about $750 on BTC. Fees make anything near that poor value.
Monthly by default: weeklies lose far more of the premium to fees and the spread,
and the fee gate refuses them on small notes.

## Say to the owner

"If ETH is below $2,300 on 30 October, you pay $2,300 each for 2.17 ETH - at $2,000
that is about $650 more than they are worth, and the $56 does not cover it. If it is
above, your $4,991 earns **$55.76** over 23 days. The money is locked until then."

Nothing clears: "Nothing worth doing today - the market is wide; you would give away
too much to get filled."

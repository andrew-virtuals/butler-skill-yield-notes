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
- **Which asset is theirs to name.** `screen` says which assets can carry a note today;
  it is not a menu. Never lay out APRs side by side. If more than one is `tradeable`,
  name them and ask which they would happily own lower, then quote that one.
- **How much, in one asset.** The collateral is locked until expiry. Getting out
  early means buying the note back, which can cost more than it brought in.
- **A strike or day they named** goes in as `--strike` and `--expiry` (`YYYY-MM-DD`),
  never a rule that lands near it. A quote whose `strike` or `expiry` is not what they
  named is not offered; an expiry without that strike is refused with the strikes it
  lists, so say those and ask.

## The first-time check

Before an owner's first note ever, get three plain yes answers. If any is no or
vague, do not quote:

- "If ETH falls hard, you end up paying the strike for it, at a loss. Clear?"
- "Your money is locked until the expiry date. Getting out early means buying the
  note back, and that can cost more than you were paid. Clear?"
- "The premium is yours whatever happens. The collateral is not. Clear?"

These yeses, and a "go ahead" with them, are not a yes to a trade. Nothing is filed,
not even the deposit, until the quote has been offered and the ownership question
answered yes.

## Saying a note out loud

Every number below is a **field on the sell quote**. Nothing here is computed by the
model. If a sentence needs a number the quote does not carry, the sentence is wrong.

| In the sentence | Field |
| --- | --- |
| the bad case: "if ETH falls 25% to $1,844" | `bad_case.fall_pct`, `bad_case.price` |
| what they are down there, premium counted | `bad_case.loss_usd` |
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

Four beats, in this order. The bad case comes first, with a dollar figure from
`bad_case`, before any premium, APR or fee is said.

1. **The bad case.** "If ETH falls 25% to $1,844 by 30 October, you still pay $2,200
   each for 0.13 ETH, and you are down about $44, even after the premium."
2. **The money, and the date.** "In return you are paid $2.12 now, after a $0.60
   fee, and it is yours whatever happens."
3. **The good case.** "If ETH is above $2,200 on 30 October, you keep the $2.12 and
   your $286 is free again."
4. **What is locked.** "Your $286 cannot be touched until 30 October."

`apr_pct`, if said at all, comes after all four, with its condition (below).

Then the ownership question, **on its own**, in the asset's terms, after the offer
and before any card: "Happy to own 0.13 ETH at $2,200 on 30 October?" A yes to the
yield is not a yes to this; never fold it into "shall I go ahead?".

## A no to owning it

A no, a "maybe", or a yes to the money with a no to the asset ends selling. Say so in
one line and stop. Every cash-secured put on that asset carries the same promise, so
do not offer another strike, tenor or size, and do not suggest or invite another asset:
"if there's an asset you'd be happy to own, I can quote that" is an invitation, and so
is pointing them at buying a call. Stop at the one line. Only if the owner names an
asset they *would* own, unprompted, start again from the top for that one.

## Words

| Do not say | Say |
| --- | --- |
| "yield", "APY", "earning 16%" | "earns $2.12 over 24 days - about 16% a year if you kept doing it", after the bad case |
| "if assigned" | "you pay $2,200 for each ETH" |
| "risk of loss" | "if ETH falls 25% to $1,844 you are down about $44" (`bad_case`) |
| "capital is deployed" | "your $286 is locked until 30 October" |
| "collect premium" | "the $2.12 is yours once it fills, whatever happens" |
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

An owner who hears "16% a year" without hearing that the spread took part of the
premium has been told half of it.

## Settlement and delivery

**Derive and Paradex settle in cash.** An in-the-money put reduces USDC by (strike - settlement
price) x size; it does not deliver ETH. "You now own ETH at $2,300" is true only after
a separate spot buy has filled. `options-lifecycle` never buys: it only reports, and
is filed with `movesFunds: false`, so the owner gets no spending-limit card.

Only when the owner asked before the open to end up owning the asset, file
`options-put-delivery@1` instead of `options-lifecycle` (never both), in SKILL.md step
7. It watches the same way and buys the asset if the put is assigned:

```json
{"recipe": "options-put-delivery@1", "title": "Watch {INSTRUMENT}, buy {UNDERLYING} if assigned",
 "triggers": [{"kind": "timer", "intervalSeconds": 900}],
 "spendBasis": {"perTrade": "COLLATERAL_USD", "times": 1},
 "params": {"VENUE": "<venue>", "INSTRUMENT": "<instrument>", "UNDERLYING": "<prefix>",
 "TOKEN_ID": "<pin>", "STRIKE": <strike>, "SIZE": <filledSize>,
 "PREMIUM_USD": <netPremiumUsd>, "COLLATERAL_USD": <collateral>}}
```

`TOKEN_ID` is the token it buys: ETH is `native:8453`; BTC is the verified, non-stock
Base row of `bevo-read token-search BTC` as `<address>:8453` (ask if two fit). It
spends, so a spending-limit card opens on the collateral: tell the owner that holding
it lets the buy go through at settlement, and that without it the buy waits for their
approval then.

The premium and the freed collateral stay in the Derive account until withdrawn.

**Rysk settles physically**: an assigned put delivers the asset itself, so there is no
delivery buy there: always `options-lifecycle` (`references/rysk.md`).

## Buying back early

A sold note shows in `acp options account` positions with a **negative** `size`.
Buying it back ends it before expiry and frees its collateral. Quote it with
`quote --side buyback --instrument <name> --size <size as a positive number>
--premium-received <USD>`, where the premium is the open's `netPremiumUsd` (or the
duty's `PREMIUM_USD`) scaled to the size being bought back.

Say `total_cost_usd`, then `result_usd`, plainly when it is negative: "Buying it back
now costs about $4.46 with fees. You were paid $3.00 for it, so you would take a $1.46
loss now." Give any `warnings` as written. Then say what waiting does: holding to
expiry costs nothing to do, and the note may still expire worthless. Then ask for the
ceiling, the most they will pay, with `max_cost_usd` as the suggestion; file only the
ceiling they agreed, quote again after their answer, and never raise it without
asking. The size is at most what they sold (the negative `size`, as a positive
number); asked for more, say what they hold and ask.

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

The smallest note is the quote's `min_size` x the strike, so it moves with the strike; a
smaller one is refused with what the minimum needs (`collateral too small`). Fees make
anything near it poor value.
Monthly by default: weeklies lose far more of the premium to fees and the spread,
and the fee gate refuses them on small notes.

## Say to the owner

"If ETH falls 25% to $1,844 by 30 October, you still pay $2,200 each for 0.13 ETH and
are down about $44, even after the premium. In return you are paid **$2.12** now, after
a $0.60 fee. If ETH is above $2,200 then, you keep it and your $286 is free again;
until then it is locked." Then, on its own: "Happy to own 0.13 ETH at $2,200 on 30
October?"

A no to that, and nothing after it: "Then a put is not for this money - every one is a
promise to buy. I won't file anything."

Nothing clears: "Nothing worth doing today - the market is wide; you would give away
too much to get filled."

---
name: yield-notes
description: Get paid to wait - sell a fully collateralised option on Derive so idle USDC earns while it waits to buy a dip, or a long ETH bag earns while it waits to sell a rally.
version: 0.1.0
metadata: {"butler":{"moneyMoving":true,"keywords":["yield","earn on my usdc","make my money work","idle cash","covered call","cash secured put","sell options","premium","get paid to wait","buy the dip","yield note","options income"],"requires":{"bins":["python3","bevo-read"]}}}
---

## When to use

Your owner has money sitting still and wants it to earn: "earn yield on my USDC",
"make my money work", "my ETH just sits there", "get paid to buy the dip", "what can
I earn on this".

A note is one option, sold short, **fully collateralised**:

| Note | What your owner is agreeing to | Collateral |
| --- | --- | --- |
| Earn on USDC | Buy the asset at a lower price if it falls there. Keep the premium either way. | USDC, strike x size |
| Earn on ETH | Sell the asset at a higher price if it rises there. Keep the premium either way. | The asset itself |

This is not lending and it is not a vault. Your owner is **selling someone else
insurance** and keeping the fee. The premium is certain. What they own at expiry is
not.

Not this skill: buying options, spreads, collars, anything on leverage, or any note
on an asset the screen does not clear. It never picks a note *for* them.

## Before you start

Three things, and the third is the one that goes wrong.

1. **Which way.** Idle USDC that would happily buy a dip is a put. A long bag they
   would happily trim into strength is a call. If neither is true, there is no note
   here - say so and stop.
2. **How much, in one asset.** The collateral is locked until expiry. Nothing else
   can spend it, and there is no early exit in v1.
3. **Say the bad outcome first, in their words, before any yield number.** Not "if
   assigned" - *"ETH drops to $2,200, and you have bought it at $2,450 anyway. You
   are down about $400, and the $56 does not cover that."* An owner who has not said
   that sentence back to you has not understood the note.

### The first-time check

Before an owner's first note ever, get three plain yes answers. Not a disclosure, a
conversation. If any answer is no or vague, do not quote:

- "If ETH falls hard, you end up owning it at the strike, at a loss. Clear?"
- "Your money is locked until the expiry date. No early exit. Clear?"
- "The premium is yours whatever happens. The collateral is not. Clear?"

## Procedure

1. [ADAPT] Read what they hold, so the offer is about their actual money:

   ```sh
   bevo-read assets
   ```

2. [FIXED] Write the script in `references/helper.md` to a file, then ask the venue
   what is sellable right now. Never assume an asset is quotable because Derive
   lists it:

   ```sh
   python3 /tmp/derive_helper.py screen --tenor monthly --collateral <THEIR_USD>
   ```

   Every row comes back with `tradeable` and, when false, a plain-English `reasons`.
   **Offer only `tradeable: true` rows.** Most days that is ETH and BTC alone.

3. [FIXED] Quote the one they want. The strike rule is a rule, never a number you
   chose:

   ```sh
   python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying ETH \
       --collateral 5000 --tenor monthly --otm-pct 10
   ```

   Use `--delta 0.20` instead of `--otm-pct` when the owner wants the odds held
   steady rather than the distance.

4. [ADAPT] Offer it in two sentences and a bad case, using **only** numbers from the
   quote object. `references/notes.md` has the shape. Never compute a premium, an APR
   or a breakeven yourself - every one of them is a field.

   Show `apr_pct` as "if you kept doing this all year", never as a rate they are
   being paid. Show `fee_usd` as its own line. If `edge_vs_fair_vol_pts` is worse
   than -3, say plainly that the market is wide today and they are not getting a
   great price.

5. [ADAPT] Get a **separate** yes to the ownership question, in the asset's own
   terms: *"Happy to own 2.04 ETH at $2,450 on 30 October?"* A yes to the yield is
   not a yes to this. Do not carry one into the other.

6. [FIXED] **Stop here and say so.** Opening a note is not live yet: there is no
   `acp options` money command, and the helper has no session key to sign with.
   Running any `open` path prints the reason and exits non-zero.

   Tell the owner plainly that Butler can price the note but cannot open it yet, and
   do not leave them thinking one was filed:

   > "I can price this one properly - $54 over 24 days on your $5,000 - but I can't
   > open it for you yet. The options plumbing isn't live. Nothing has been bought."

   Never describe a quote as a position, and never file a lifecycle duty for a note
   that does not exist.

## Idempotency and retries

Screening and quoting are free reads - re-run them rather than reasoning from a quote
that is seconds old. **Quotes go stale in about a minute** (`valid_until`); past that,
quote again before showing a number.

Opening is a different matter. When the money path does go live: one
`--idempotency-key` per approved note, and if a fill is uncertain **do not re-run
it** - a retried money command can sell the note twice. Look it up instead:

```sh
bevo-read request <KEY>
```

Two notes funded from one pot of collateral is the failure that matters here: the
second one is uncollateralised, and Derive's margin engine will happily allow it.

## Failure handling

| Outcome | What to do |
| --- | --- |
| `screen` returns nothing tradeable | Say no note is worth doing today and why, in their words. Offer to look again tomorrow. Never loosen the gate to find one. |
| `no live bid` | Nobody is buying that option. Not a retry - pick another expiry or asset. |
| `market is N vol points wide` | The price on offer is poor. Say so and stop; do not sell into it because the APR looks good. |
| `fees are N% of the premium` | The ticket is too small or the tenor too short. Offer a monthly, or a bigger note. |
| `collateral too small` | Below Derive's own minimum. Give the real figure from the reason and offer that. |
| Quote expired at approval | Re-quote and re-offer. Never open on a stale number. |
| Fill came back worse than `min_premium` | It should have failed. Report it as a venue problem and stop trading until someone looks. |
| Derive unreachable | Say Butler cannot see the options market right now and quote nothing. |

## Limits

- One leg, sold, fully collateralised. No spreads, no leverage, no buying.
- **Monthly tenors.** Weeklies lose about a third of the premium to fees and the
  spread at retail size; the helper rejects them below roughly $8,000.
- Minimum note is Derive's own: about $245 of collateral on ETH, about $780 on BTC.
  Any per-note cap below that cannot be filled at all.
- Collateral is locked until expiry. No early close in v1.
- Every number here is read off the **public order book**. Derive's RFQ path usually
  prices better - a quarter of the premium is lost crossing the public spread - but
  it needs a session key, so the prototype cannot use it. Treat a quote here as the
  worst case, not the best available.
- **Derive settles in cash.** An in-the-money put reduces USDC - it does not deliver
  ETH. Only the optional post-settlement buy makes "you now own ETH" true. Say which
  is happening.
- The premium lands in the Derive subaccount, not their wallet.
- Not advice. Offer what passes the screen; never rank by APR and never recommend.

## Say to the owner

Lead with the money, name the date, then the bad case with equal weight:

"Your $5,000 USDC can earn **$54** over the next 24 days - about **16% a year** if
you kept rolling it. If ETH is above $2,450 on 30 October you keep the $5,000 and the
$54. If it is below, you have bought 2.04 ETH at $2,450. Fees are $2.16, already
taken off. Your money is locked until then."

When nothing clears the screen: "Nothing worth doing today - the options market is
wide, and you would be giving away about a quarter of the premium to get filled. I
will look again tomorrow."

At expiry, never make them ask: "ETH closed at $2,780. You kept your $5,000 and the
$54. Roll it for November?"

---
name: yield-notes
description: Get paid to wait - sell a fully collateralised option on Derive so idle USDC earns while it waits to buy a dip, or a long ETH bag earns while it waits to sell a rally.
version: 1.0.0
metadata: {"butler":{"moneyMoving":true,"keywords":["yield","earn on my usdc","make my money work","idle cash","covered call","cash secured put","sell options","premium","get paid to wait","buy the dip","yield note","options income"],"requires":{"bins":["python3","bevo-read","acp"]}}}
---

## When to use

Your owner has money sitting still and wants it to earn: "earn yield on my USDC",
"make my money work", "get paid to buy the dip", "what can I earn on this".

A note is one option, sold short, **fully collateralised**:

| Note | What your owner is agreeing to | Collateral |
| --- | --- | --- |
| Earn on USDC (cash-secured put) | Buy the asset at a lower price if it falls there. Keep the premium either way. | USDC, strike x size |
| Earn on ETH (covered call) | Sell the asset at a higher price if it rises there. Keep the premium either way. | The asset, in the Derive account |

This is not lending and not a vault. Your owner is **selling someone else insurance**
and keeping the fee. The premium is certain. What they own at expiry is not.

Not this skill: buying options, spreads, anything on leverage, or a note on an asset
the screen does not clear. It never picks a note *for* them.

## Before you start

1. **Which way.** Idle USDC that would happily buy a dip is a put. `acp options
   deposit` moves USDC only, so a covered call opens only when the asset is already in
   the Derive account; otherwise say a call is not available here and stop.
2. **How much, in one asset.** The collateral is locked until expiry. No early exit.
3. **The bad outcome first, in their words, before any yield number.** Not "if
   assigned" - *"ETH drops to $2,000, and you have bought it at $2,300 anyway. You are
   down about $650, and the $56 does not cover that."*

Money commands need Butler's server signer on the owner's wallet, and run from chat
only - never from a duty.

### The first-time check

Before an owner's first note ever, get three plain yes answers. If any is no or
vague, do not quote:

- "If ETH falls hard, you end up paying the strike for it, at a loss. Clear?"
- "Your money is locked until the expiry date. No early exit. Clear?"
- "The premium is yours whatever happens. The collateral is not. Clear?"

## Procedure

1. [ADAPT] Read what they hold, and their Derive account:

   ```sh
   bevo-read assets
   acp options account
   ```

   `signerReady: false` - stop: the owner must enable Butler's signer first. Note
   `account.freeForNewPutsUsd` (free USDC on Derive; `exists: false` means no account
   yet) and `ethereum.usdc`. An unreadable account is not an empty one.

2. [FIXED] Write the script in `references/helper.md` to `/tmp/derive_helper.py`,
   then screen. Never assume an asset is quotable because Derive lists it:

   ```sh
   python3 /tmp/derive_helper.py screen --tenor monthly --collateral <THEIR_USD>
   ```

   **Offer only `tradeable: true` rows**, with their `reasons` for the rest.

3. [FIXED] Quote the one they want. The strike is a rule, never a number you chose:

   ```sh
   python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying <ASSET> --collateral <USD> --tenor monthly --otm-pct 10
   ```

   `--delta 0.20` in place of `--otm-pct 10` holds the odds steady instead.

4. [ADAPT] Offer it: the bad case first, then the money, using **only** fields of
   the quote (`references/notes.md` maps each). Never compute a premium, an APR or a
   breakeven. `fee_usd` is its own line; `apr_pct` is "if you kept doing this all
   year", never a rate paid. If `edge_vs_fair_vol_pts` is worse than -3, say the
   market is wide today.

5. [ADAPT] Get a **separate** yes to the ownership question, in the asset's terms:
   *"Happy to own 2.17 ETH at $2,300 on 30 October?"* A yes to the yield is not a yes
   to this. Derive settles in cash; the asset is bought for them after settlement only
   if they ask for that now.

6. [FIXED] Fund only when `freeForNewPutsUsd` is below `collateral.amount`. Deposit
   the shortfall rounded up to the cent, never under $5 (Derive keeps a smaller
   deposit). If `ethereum.usdc` is short of that, bridge the difference from Base
   first; each command files an approval card for the owner:

   ```sh
   acp trade --token-in usdc --chain-in 8453 --amount-in <BRIDGE_USDC> --token-out usdc --chain-out 1 --idempotency-key <NOTE>:bridge
   acp options deposit --amount <DEPOSIT_USDC> --idempotency-key <NOTE>:deposit
   ```

   Run the deposit only after the bridge is confirmed, for what `acp options account`
   then shows as `ethereum.usdc`, up to the shortfall. Credit lands about two minutes
   after the deposit is mined: re-read the account until `freeForNewPutsUsd` covers
   the note. If it ends up short, re-quote with `--collateral` at what is free and
   re-offer.

7. [FIXED] Quote again if `valid_until` has passed, then open with the quote's own
   fields, one key per note:

   ```sh
   acp options open --instrument <instrument> --size <size> --min-premium <min_premium_usd> --max-collateral <collateral.amount> --idempotency-key <NOTE>:open
   ```

   `min_premium_usd` is 95% of `net_premium_usd`, rounded down. The reply is an
   approval card, not a fill: tell the owner to approve it in the app. Nothing is sold
   yet.

8. [FIXED] Wait for the outcome. Butler's server posts it as a note in this chat
   ("Sold 2.17 ETH-20261030-2300-P for $55.76 after fees…"), or look it up:

   ```sh
   bevo-read request <NOTE>:open --route options
   ```

   `approvalStatus: confirmed` is executed. `failed`, `rejected` or a no-fill: nothing
   was sold and nothing is locked - say so. `pending` or `signed`: still waiting.

9. [FIXED] Only for a confirmed open, file the lifecycle duty with `duty_create`,
   settings copied from the **fill**, never the quote:

   ```json
   {"recipe": "options-lifecycle@2",
    "params": {"INSTRUMENT": "ETH-20261030-2300-P", "PRODUCT": "cash_secured_put",
               "UNDERLYING": "ETH", "STRIKE": 2300, "SIZE": 2.17,
               "PREMIUM_USD": 55.76, "COLLATERAL_USD": 4991},
    "triggers": [{"kind": "timer", "intervalSeconds": 900}]}
   ```

   Those are the example's numbers; yours come from the outcome note. A fill can be
   partial ("of 2.17 approved"): SIZE is what was sold, PREMIUM_USD what was received
   after fees, `COLLATERAL_USD` is STRIKE x SIZE for a put and `0` for a call. Turn
   `DELIVER_ASSET` on only if the owner asked in step 5. Never file for an unknown,
   refused or pending open; a fill number you cannot read means no duty, and say so.

10. [FIXED] Withdraw only when asked, only free USDC (`freeForNewPutsUsd`; collateral
    behind an open note cannot leave). It pays to the owner's wallet on Ethereum in
    about 20 minutes, less up to $1; bringing it back to Base is a second card:

    ```sh
    acp options withdraw --amount <USDC> --idempotency-key <NOTE>:withdraw
    acp trade --token-in usdc --chain-in 1 --amount-in <USDC_ARRIVED> --token-out usdc --chain-out 8453 --idempotency-key <NOTE>:home
    ```

    Bridge only after the withdrawal has arrived in `ethereum.usdc`.

## Idempotency and retries

Screening and quoting are free reads: re-run them rather than reason from a quote
past `valid_until` (60 seconds).

Every money command carries a key derived once per note, such as
`yn:eth:20261030:2300p:1`, with `:bridge`, `:deposit`, `:open`, `:withdraw`, `:home`.
On an error, a timeout or an unclear answer, **do not re-run it** - a retried open can
sell the note twice. Look it up instead:

```sh
bevo-read request <KEY> --route options
```

The bridge legs are `acp trade`: look them up with `--route trade`. `not_found` means
nothing was filed under that key. Two notes funded from one pot of collateral is the
failure that matters; the server refuses an open that free USDC does not cover.

## Failure handling

| Outcome | What to do |
| --- | --- |
| `screen` returns nothing tradeable | Say no note is worth doing today and why, in their words. Never loosen a gate to find one. |
| `no live bid`, `market is N vol points wide` | Nobody is paying a fair price. Pick another asset or expiry, or stop. |
| `fees are N% of the premium` | Ticket too small or tenor too short. Offer a monthly, or a bigger note. |
| `collateral too small` | Below Derive's minimum. Give the figure from the reason. |
| `OPTIONS_SIGNER_NOT_READY` | Butler's signer is not enabled on their wallet. Say it must be enabled first, and stop. Nothing was filed. |
| `OPTIONS_CHAT_ONLY` | A duty tried a money command. Only chat can open, deposit or withdraw. |
| `OPTIONS_BOUNDS_MISMATCH` | `--max-collateral` is below what the note locks. Re-quote; never raise it past what the owner agreed. |
| Open failed: no fill | Nothing was sold and nothing is locked. The price moved under `min_premium_usd`; re-quote and re-offer, never lower the floor quietly. |
| Open failed: not enough free USDC | Fund (step 6) or re-quote smaller. |
| Card swept after 30 minutes | It failed unsigned. Re-quote before offering again. |
| Derive or the account unreachable | Say Butler cannot see the options market or the account right now. Quote nothing; guess nothing. |

## Limits

- One leg, sold, fully collateralised. No spreads, no leverage, no buying.
- **Monthly by default.** Weeklies lose far more of the premium to fees and the
  spread; the fee gate refuses them on small notes.
- Smallest note is Derive's minimum size x the strike: about $230 on ETH at today's
  strikes, about $750 on BTC. Fees make anything near that poor value.
- Collateral is locked until expiry. **No early close.**
- **Derive settles in cash.** An in-the-money put reduces USDC; it does not deliver
  ETH. Say "you now own ETH" only after a buy has filled.
- The premium and the freed collateral stay in the Derive account until withdrawn.
- Prices are the public order book. Treat a quote as the worst case.
- Not advice. Offer what passes the screen; never rank by APR and never recommend.

## Say to the owner

Bad case and money together, with the date:

"If ETH is below $2,300 on 30 October, you pay $2,300 each for 2.17 ETH - at $2,000
that is about $650 more than they are worth, and the $56 does not cover it. If it is
above, your $4,991 USDC earns **$55.76** over 23 days - about **18% a year** if you
kept rolling it. Fees are $2.18, already taken off. The money is locked until then."

After a fill: "Sold - $55.76 is yours. I'll tell you a day before it settles."

When nothing clears: "Nothing worth doing today - the options market is wide, and you
would give away too much of the premium to get filled. I will look again tomorrow."

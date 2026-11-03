# A resting order: their price, on the book

An ordinary open, buy or close takes what the book pays **now**, inside the bound the
owner agreed, and cancels the rest. A **resting order** waits on Derive's or Paradex's
book at the owner's own price per contract until it fills, they cancel it, or the
option expires. Rysk has no book, so it has none.

It is the owner's choice, never Butler's: offer it only when they ask to wait for a
price ("sell it at $41 or better", "leave a limit order", "only if it gets to $80").

## Two kinds

| `--order` | What it does | When |
| --- | --- | --- |
| `gtc` | Waits at their price; if the book already pays that, it fills at once | The default for "at my price" |
| `post-only` | The same, but refused if it would fill at once | Only when they asked never to take the book |

No other kind: a market order has no price they agreed to.

## The command

SKILL.md step 5's command, with the total bound swapped for `--order gtc` (or
`--order post-only`) and their price per contract:

| Trade | Instead of | Add |
| --- | --- | --- |
| Open (sell a put) | `--min-premium` | `--order gtc --min-price <THEIR_PRICE>`; keep `--max-collateral` |
| Buy | `--max-cost` | `--order gtc --max-price <THEIR_PRICE>` |
| Sell back (Paradex only) | `--min-proceeds` | `--order gtc --min-price <THEIR_PRICE>` |
| Buy back (Paradex only) | `--max-cost` | `--order gtc --max-price <THEIR_PRICE>` |

Never both a price and a total: the server refuses it.

**A close waits only on Paradex.** Derive closes at once or not at all, so never offer a
Derive sell-back or buy-back "at their price": say Derive cannot leave a close on the book,
and offer to close now at a floor or ceiling they name (SKILL.md step 3).

## The price

- **Per contract, before fees.** `--min-price` sells (an open, a sell-back),
  `--max-price` buys (a buy, a buy-back). It is their number: say it back with the
  side, "you sell at $41 or more for each ETH of the put", and get a yes.
- Quote first, as for any trade, and still say the bad case: a resting sale is the same
  promise to buy the asset at the strike once it fills. The quote's `premium_usd` (the bid
  now, for the size) says how far their price is from filling. Never move their price toward them unasked.
- An open still needs `--max-collateral` (`collateral.amount`): the collateral is held
  from the moment the order is placed, not only once it fills, so free USDC drops at
  once.
- **A resting buy holds money too:** their price x size, from the moment it is placed,
  until it fills or is cancelled. Say that figure before the yes ("$3.82 is set aside
  from now"). A sell-back holds nothing.
- **A price inside the venue's band only.** Paradex refuses a price far from its mark
  (about ±40%); the card fails and nothing rests.

## Once approved

The card is **placed, not filled**: `approvalOutcome.resting` is `true`, with
`order.orderId`, `orderType`, `limitPricePerUnitUsd`, and `filledSize` (often 0) and
`remainingSize`. Say it is waiting on the book at their price, until when (the expiry),
and that they will hear when it fills. The server watches it and tells them once on
the first fill and once when it ends. Never poll it, never re-file it.

A `gtc` order the book already pays fills at once and reads like any fill. A `post-only`
order that would have filled is refused: nothing rests, nothing is locked.

`acp options account` lists every resting order under `resting orders (… held back …)`,
with its id, side, size, price and how much has filled.

An order's state changes without you hearing: the owner can cancel it with the Cancel hold
in the app, it can fill, or the option can expire, and the server's notes about it go to
the owner, not to you. Never say where an order or position stands from earlier in the
conversation. Read `acp options account --venue <venue>` first and say what it shows; an
order no longer under `resting orders` has ended.

## The lifecycle duty

Filed when the order is placed, not on a fill (SKILL.md step 7's `duty_create`, with
`"ORDER_ID": "<order.orderId>"`): it waits while the order rests, watches what the
account holds from the first fill, at what it cost, and finishes quietly if the order ends with nothing filled. SIZE is the whole order,
PREMIUM_USD their price x size, COLLATERAL_USD strike x size for a put (else 0); the
account's figures replace them as it fills. Never delete it on a cancel: it finishes
itself.

## Cancelling

Only when they ask, and only the order they name, by the id `acp options account` lists
under `resting orders`:

```sh
acp options cancel --order <ORDER_ID> --idempotency-key <KEY>:cancel
```

It files a card like any trade: tell the owner to approve it in the app, and that until
they do **the order stays on the book and can still fill** at their price. Approved, it
comes off; whatever had filled stays filled, and is theirs as any fill is. The server
tells them how it ended; never re-file the cancel to find out (step 6 reads the card).
Their own Cancel hold on the order's card in the app needs no card from you.
`OPTIONS_ORDER_NOT_FOUND` or `OPTIONS_ORDER_CLOSED`: it had already filled, been
cancelled or expired, and nothing is filed. Read the account and say what it shows.

## Say to the owner

"I'll leave an order to sell the $2,200 put for $41 or more per ETH, 0.5 ETH, on
Derive. It waits on the book until someone pays that, you cancel it, or it expires on 30
October. $1,100 is set aside from now; if it fills you are paid at least $20.50 before
fees, and you may end up buying 0.5 ETH at $2,200. You'll hear when it fills. Yes?"

A buy: "I'll leave an order to buy the $2,600 call for $19.10 or less per ETH, 0.2 ETH,
on Derive. It waits until someone sells at that, you cancel it, or it expires on 27
November. $3.82 is set aside from now. If it fills you pay at most $3.82 plus Derive's
fee, and you can lose all of it. Yes?"

Placed: "It's on the book at $41 or more, nothing filled yet. I'll let you know when it
does."

Cancel filed: "I've put the cancel in your Approvals. Until you approve it, the order is
still on the book and can still fill at $41."

Cancelled: "Your order is off the book. Nothing had filled, so the $1,100 is free again."

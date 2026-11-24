# A worked order: a better price than the book, given time

An ordinary open or buy takes the book now: a seller gets the bid, a buyer pays the ask.
The `options-order-manager@1` duty **works** the same trade instead: it asks Derive's
market makers, rests an order at Derive's own mark, and gives ground toward the book
step by step, never past the price the owner agreed. Most orders a maker will take fill
in the first minute; the rest wait, and may not fill at all.

It is the owner's choice, never Butler's: offer it only when they ask for a better
price or to take their time ("get me a better price", "work the order", "don't just pay
the ask", "no rush"). **Derive only**, a cash-secured put sold or an option bought.
Paradex and Rysk: say it works on Derive only.

## What is different, said before the yes

1. **It trades from a wallet of its own.** The money leaves their main wallet on one
   funding card, and from then on the duty trades with no further approval, inside the
   worst price they agreed.
2. **It may not fill.** If the market moves away, nothing trades by the deadline and the
   money waits in that wallet's Derive account.
3. **What it buys or sells stays in that account**, shown as its own Platforms row
   ("Derive · <the duty's title>"), not with their main Derive positions.

SKILL.md's "Never file without all four" holds unchanged: the bad case first, the plain
yes, and a quote run after their last answer.

## Filing it

1. Quote as SKILL.md step 2. A Derive quote carries `worked`:

   | Field | Means |
   | --- | --- |
   | `worked.params` | the duty's settings, passed as they are. `WORST_PRICE` is the book's price per contract now: the bid selling, the ask buying |
   | `worked.fund_usdc` | what the duty's wallet starts with: the collateral or the cost, plus the fee and 2% for the bridge, never under $12 |
   | `worked.at_mark_saves_usd` | the most working it could save: a fill at Derive's mark. Say "up to", never as a promise |

   No `worked`: the quote is not Derive's, or has no live price; it cannot be worked.
2. Offer it with step 3's sentences, then the three points above, the worst price
   ("never under $41 for each ETH" selling, "never over $50" buying), how long
   (`WORK_MINUTES`, theirs; 240 if they name none, 15 for "quick"), and `fund_usdc`.
   A worse `WORST_PRICE` only if they name it. Get a yes.
3. A new wallet for it, then the duty:

   ```sh
   bevo-wallet create --chain ethereum --label <LABEL> --idempotency-key <KEY>:wallet
   ```

   ```json
   {"recipe": "options-order-manager@1", "movesFunds": true, "title": "Work {INSTRUMENT} for a better price",
    "walletId": "<LABEL>", "fundUsdc": <worked.fund_usdc>,
    "triggers": [{"kind": "timer", "intervalSeconds": 60}],
    "params": {<worked.params>, "WORK_MINUTES": <minutes>}}
   ```

   One wallet per worked order, never one that holds money or serves another duty.
   Tell the owner to approve the funding card. No `acp options` command is filed from
   the chat. Make sure SKILL.md step 9's `options-lifecycle` duty exists: it watches
   what this wallet's account holds to expiry, as it does every other option.
4. The duty tells the owner when it starts, on each part fill, and at the end with a
   receipt: the average price, what that saved against the book, and where each fill
   came from. Then it finishes. Never poll it; `duty_show` and `duty_logs` when they
   ask how it is going.

## Stopping it

**Never turn it off to stop it.** Turned off while an order rests, that order stays on
Derive and can still fill at its price until the option expires.

"Cancel it", "stop working it": `duty_update` its params with `"STOP": true` added,
every other setting unchanged. Within a minute it cancels what rests and sends the
receipt for what had filled. Found turned off with an order still resting: cancel it from
chat, `acp options cancel --order <id> --wallet <LABEL>`, a card (`--wallet` left out in
the duty's own chat).

## Afterwards

- **Look:** `bevo-read get '/options/account?venue=derive&walletId=<LABEL>'`.
- **Close what it holds:** quote the close (step 2); to work it, `duty_update` the same
  duty with that quote's `worked.params` (a new order; a close is worked by the makers
  and the book only). To close now: step 5's `acp options close … --wallet <LABEL>`, a card.
- **Bring the money home:** `account.md` § A duty's own wallet: out of Derive into this
  wallet, then into the main wallet, a card each. `duty_delete` is refused until then.
- At expiry Derive settles in cash into that same account; the lifecycle duty gives
  the heads-up and the outcome, naming this wallet.

## Say to the owner

"Instead of paying the $50 ask now, I can work it: ask Derive's market makers and wait
at a better price for up to 4 hours, never paying over $50 for each ETH. It could save
up to $1.00; it may also not fill, and then nothing is bought. It trades from a wallet
of its own that you fund once with $53, with no approval after that, and what it buys
stays in that wallet's Derive account. You can lose all of what it pays. Yes?"

Filed: "It's set up. Approve the $53 funding card and it starts; you'll hear when it
fills or when the 4 hours are up."

Stopped: "I've told it to stop. It takes its order off the book within a minute and
sends you what filled."

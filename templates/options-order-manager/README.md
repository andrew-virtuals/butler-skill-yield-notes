# options-order-manager

Works one Derive options order for a better price than filling it at once (the bid
selling, the ask buying): it asks the makers, rests at Derive's mark, and gives ground
toward the book slowly, never past the worst price the owner agreed to. It trades
hands-free from **the duty's own butler wallet** (`DUTY_WALLET_OPTIONS_ENABLED`): one
funding card, and none after it.

## How it is filed

With `walletId` and `fundUsdc`: an empty EVM butler wallet bound to the duty, funded
with what the order needs (a sold put's `strike x SIZE`, a buy's `WORST_PRICE x SIZE`
plus the fee) plus 2%. Trigger `{"kind": "timer", "intervalSeconds": 60}`.
Settings come from the fill-now quote; `WORST_PRICE` is its price per contract, or the
worse price the owner named. For a quick order set `WORK_MINUTES` (15, say).

## What it does

It first deposits its USDC on Derive. The target is the mark moved toward the book by `(step / steps)²`
of the gap, never past `WORST_PRICE`. A resting order is pulled on prices older than 2
minutes, and for 15 minutes after a 0.3% index move against it within 5. Then the first
of these that applies, and the next while the minute lasts (3 commands at most):

| When | It sends |
| --- | --- |
| a new step, and at the start | `--order rfq` for all that is left (a resting order is cancelled first) |
| the book reaches the target | an RFQ the makers must beat it on, then immediate-or-cancel |
| nothing rests (not a close) | `--order post-only` at the target |
| the target moved over 1% and 1.5 ticks | a cancel, then the order again |

**A maker is taken** at the target, or at once when the quote saves `TAKE_SAVING` of the
gap between the book and the mark; never at a price worse than the book's. Makers do not
see the bound, and the fill is at their price. A refused RFQ names the best quote; the
duty asks again, 3 minutes on or more, once the mark has moved enough for it to fit.

At the deadline (`WORK_MINUTES` from the start, never later than an hour before expiry)
it cancels, asks the makers to beat the book, takes the book at `WORST_PRICE`, and
sends a receipt: the average, the saving, and where each fill came from.

It finishes there. What it holds is watched to expiry by `options-lifecycle@12`.

## What it will not do

- **Go past the worst price.** The rail refuses a fill outside each command's bound.
- **Rest a close.** Derive refuses a resting reduce-only order (11024).
- **Send a command twice.** One key per command (`om:<duty>:<order>:<n>:<op>`; `<order>`
  hashes the settings); `n` moves on once the ledger says how it ended.
- **Finish with an order resting.** It cancels any order in its account but the one
  it works.

## What to know

- **Stop it with `STOP`, never by pausing.** Only the running duty can cancel its
  wallet's resting order: the chat cannot. Paused while one rests, the order stays on
  Derive until it expires or the duty runs again.
- **The position stays in the duty wallet's Derive account.** Closing it is a chat
  command with `--wallet`, or this duty, `ACTION: close`.

## Settings

| Name | Unit | Means |
| --- | --- | --- |
| `INSTRUMENT` | Derive's name | `ETH-20261128-3000-P` |
| `ACTION` | `open` \| `buy` \| `close` | sell to open, buy, or close what the account holds |
| `SIZE` | contracts | the whole order |
| `WORST_PRICE` | US dollars a contract, before fees | a sale never under it, a buy never over it |
| `FEE_USD` | US dollars | the fill-now quote's `fee_usd` for SIZE |
| `WORK_MINUTES` | minutes, default `240` | how long to work it |
| `STEP_MINUTES` | minutes, default `WORK_MINUTES / 8` (1 to 30) | how often it gives ground and asks the makers |
| `TAKE_SAVING` | 0 to 1, default `0.5` | see above; `1` takes a maker only at the target |
| `SIZE_STEP`, `MIN_SIZE`, `TICK_SIZE` | | Derive's steps, from the quote |
| `FILL_NOW_PRICE` | default `WORST_PRICE` | the book's price at filing, for the receipt |
| `STOP` | `true` | cancel what rests, send the receipt, finish |

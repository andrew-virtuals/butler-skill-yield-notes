# options-account

Keeps the owner's account on one options venue on the wallet page's Platforms tab: one row named for the venue (**Paradex**), kept at what the account is worth, listing each open position. The options-trading skill files it once per owner and venue, after the first confirmed `acp options deposit --venue <venue>` or the first time `acp options account --venue <venue>` reads `exists: true`. It is the only writer of that row. Derive has its own `derive-account` duty.

## How it is filed

`{"recipe": "options-account@1", "title": "Paradex account", "params": {"VENUE": "paradex"}, "triggers": [{"kind": "timer", "intervalSeconds": 600}]}`. One per owner and venue: a second one adds nothing, because both write the same row.

A new venue is a new `VENUE` value here; the duty takes the row's name and site from bevo-server's account read (`/options/account?venue=<id>`: `name`, `site`).

## What it does

It checks once when it starts, then on every tick, a random 0 to 60 seconds after the timer fires.

| The account reads | Platforms row | Status line |
| --- | --- | --- |
| fine, every part priced | set to the account's worth, with its positions | `$<value> · <n> open` |
| `exists: false` (no deposit yet) | untouched | No deposit credited yet |
| `account: null` (Butler's signer is off) | untouched | Butler's signer is off |
| unreadable, or no `site`/`name` in the answer | untouched | Couldn't read it |
| a position with no mark, an index read that fails, or a total under 0 | untouched | Some positions unpriced |

The worth is `usdc`, plus the `valueUsd` of every bought position (`size > 0`), less the `valueUsd` of every sold one (`size < 0`, what buying it back costs), plus each collateral asset (`assets[U].held`) at the venue's index, read from `/options/ticker`. An account that reads fine and holds nothing is a real `$0`. Each position is listed as `Bought 0.1 ETH 2,550 call`, with its instrument, its signed value, when it expires and how far up or down it is.

## What it will not do

- **Write 0 for "could not read".** Every failed or partly priced read leaves the row at its last good value.
- **Send a note.** bevo-server already tells the owner about each deposit, open, buy and close, and the options-lifecycle duty about expiries and settlements.
- **Call `bevo.fail()` because the venue is down.** Each check catches its own errors and logs them.
- **Move money or touch a position.** It makes no `acp` call. It only reads.

## Trigger

`{"kind": "timer", "intervalSeconds": 600}`. The row catches up with a deposit, trade or settlement within about 10 minutes.

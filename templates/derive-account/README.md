# derive-account

Keeps the owner's Derive options account on the wallet page's Platforms tab: one row named **Derive**, kept at what the account is worth. The options-trading skill files it once per owner, after the first confirmed `acp options deposit` or the first time `acp options account` reads `exists: true`. It is the only writer of that row.

## How it is filed

`{"recipe": "derive-account@1", "title": "Derive account", "triggers": [{"kind": "timer", "intervalSeconds": 600}]}`. It takes no settings. One per owner: a second one adds nothing, because both write the same row (it is keyed by the owner's wallet).

## What it does

It checks once when it starts, then on every tick, a random 0 to 60 seconds after the timer fires.

| The account reads | Platforms row | Status line |
| --- | --- | --- |
| fine, every part priced | set to the account's worth | `$<value> · <n> open` |
| `exists: false` (no deposit yet) | untouched | No deposit credited yet |
| `account: null` (Butler's signer is off) | untouched | Butler's signer is off |
| unreadable (`503`, `404`, `429`) | untouched | Couldn't read it |
| a position with no mark, an index read that fails, or a total under 0 | untouched | Some positions unpriced |

The worth is `usdc`, plus the `valueUsd` of every bought position (`size > 0`), less the `valueUsd` of every sold one (`size < 0`, what buying it back costs), plus each collateral asset (`assets[U].held`) at Derive's index for it, read from `/options/ticker`. An account that reads fine and holds nothing is a real `$0`.

**One note: a deposit landing.** "Your Derive deposit landed: $X USDC credited. The account is worth $Y now." It is sent only when all three hold:
- `usdc` rose by $1 or more since the last good check,
- the positions are the same as at that check,
- no position has changed in the last hour, so a settlement's or a close's cash is never taken for a deposit.

The first check has nothing to compare with, so it sends no note. If it reads no account, the baseline is $0 and the deposit that creates the account gets its note.

## What it will not do

- **Write 0 for "could not read".** Every failed or partly priced read leaves the row at its last good value.
- **Call `bevo.fail()` because Derive is down.** Each check catches its own errors and logs them. The duty keeps running.
- **Send a note for anything but a deposit.** Opens, buys, closes and withdrawals each get bevo-server's own note. Expiries and settlements get the options-lifecycle duty's. A deposit followed by a trade within the same check gets no note.
- **Move money or touch a position.** It makes no `acp` call. It only reads.
- **Add a second row.** The row is keyed by the Derive site and the owner's wallet, so every check updates the same one.

## Trigger

`{"kind": "timer", "intervalSeconds": 600}`. The row catches up with a deposit, trade or settlement within about 10 minutes.

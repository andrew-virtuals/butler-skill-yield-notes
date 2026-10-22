# options-account

Keeps the owner's account on every options venue on the wallet page's Platforms tab: one row per venue whose account exists (**Derive**, **Paradex**), kept at what that account is worth, listing each open position. The options-trading skill files it once per owner, as soon as an account exists on any venue. It is the only writer of those rows, and replaces `derive-account`.

## How it is filed

`{"recipe": "options-account@1", "title": "Options accounts", "triggers": [{"kind": "timer", "intervalSeconds": 600}]}`. No settings. One per owner: a second one adds nothing, because both write the same rows. An owner still running `derive-account` has it removed when this one is filed, so each row has one writer.

## What it does

It checks once when it starts, then on every tick, a random 0 to 60 seconds after the timer fires. Each check is one read of bevo-server's `/options/account`, whose `venues` lists every venue the server trades, each with its `name`, `site`, `depositsLandLater` and `account`. A venue the server adds is written on the next check, with nothing refiled and no change here.

| A venue reads | Its row | Status line (all venues) |
| --- | --- | --- |
| fine, with a `worthUsd` | set to it, with its positions | `$<total> · <n> open` |
| `exists: false` (no deposit yet) | none yet | No deposit credited yet, if no venue has one |
| `available: false` with an `error` | untouched | `$<total> · <k> not read`, or Couldn't read it |
| no `worthUsd`, or one under 0 | untouched | as above, or No worth from the venue |
| `available: false` with a `reason` (not traded here) | none | not counted |
| `account: null` (Butler's signer is off) | untouched | Butler's signer is off |

The worth is the venue's own `worthUsd`, written as it stands: Derive's is the sum of its subaccounts' `subaccount_value`, Paradex's its `account_value`. Each position is listed as `Bought 0.1 ETH 2,550 call`, with its instrument, its signed value, when it expires and how far up or down it is.

## The one note

On a venue with `depositsLandLater` (Derive, whose deposit is bridged after its card has closed), a rise in USDC of $1 or more, with positions unchanged for an hour, is a deposit landing: "Your Derive deposit landed: $50.00 USDC credited. The account is worth $55.00 now." The first check never notes one; before the account exists its baseline is $0, so the first deposit is a rise from zero. Paradex's deposit card reports the credit itself, so it gets no note.

## What it will not do

- **Write 0 for "could not read".** Every failed or unvalued read leaves that venue's row at its last good value.
- **Do a venue's accounting.** It never adds up cash and positions itself.
- **Call `bevo.fail()` because a venue is down.** Each check catches its own errors and logs them.
- **Move money or touch a position.** It makes no `acp` call. It only reads.

## Trigger

`{"kind": "timer", "intervalSeconds": 600}`. A row catches up with a deposit, trade or settlement within about 10 minutes.

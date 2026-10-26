# options-account

Keeps the owner's account on every options venue on the wallet page's Platforms tab: one row per venue whose account exists (**Paradex**, **Rysk**), or one per subaccount where the venue splits it (**Derive**: `PRIME`, `RWA`…), kept at what that account is worth, listing each open position. The options-trading skill files it once per owner, as soon as an account exists on any venue. It is the only writer of those rows, and replaces `derive-account`.

## How it is filed

`{"recipe": "options-account@3", "title": "Options accounts", "triggers": [{"kind": "timer", "intervalSeconds": 600}]}`. No settings. One per owner: a second one adds nothing, because both write the same rows. An owner still running `derive-account` has it removed when this one is filed, so each row has one writer. A duty on `@1`/`@2`, or forked from one, is updated in place with `duty_update {"recipe": "options-account@3"}`.

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

The worth is the venue's own `worthUsd`, written as it stands: Paradex's is its `account_value`. Each position is listed as `Bought 0.1 ETH 2,550 call`, with its instrument, its signed value (a sold option is negative: what buying it back costs), when it expires and how far up or down it is. A position its venue does not mark (Rysk) has no value, as the worth counts it: the premium received and a put's collateral; once expired, "Awaiting settlement".

## Subaccounts

A venue that splits the account (`account.accounts`, Derive's risk universes) gets one row per subaccount instead, under the venue's name and site, with the subaccount's name (`PRIME`) as the row's account and its own `worthUsd` (Derive's `subaccount_value`) as the row's value. The first line is `Cash`, the subaccount's `usdc`, then its positions. Every subaccount is priced or none is written. Once all of them are saved, the venue's other rows on that site are removed: the single row keyed by the wallet that `@1` wrote, and any subaccount that is gone. A check where a row was not saved, or the rows could not be listed, removes nothing.

## The one note

On a venue with `depositsLandLater` (Derive, whose deposit is bridged after its card has closed), a rise in USDC of $1 or more, with positions unchanged for an hour, is a deposit landing: "Your Derive deposit landed: $50.00 USDC credited. The account is worth $55.00 now." The first check never notes one; before the account exists its baseline is $0, so the first deposit is a rise from zero. Paradex's deposit card reports the credit itself, so it gets no note.

## What it will not do

- **Write 0 for "could not read".** Every failed or unvalued read leaves that venue's row at its last good value.
- **Do a venue's accounting.** It never adds up cash and positions itself.
- **Call `bevo.fail()` because a venue is down.** Each check catches its own errors and logs them.
- **Move money or touch a position.** It makes no `acp` call. It only reads, and removes only its own venues' superseded rows.

## Trigger

`{"kind": "timer", "intervalSeconds": 600}`. A row catches up with a deposit, trade or settlement within about 10 minutes.

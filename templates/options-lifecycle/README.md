# options-lifecycle

Watches **every option the owner holds** to its outcome: sold or bought, on Derive, Paradex or Rysk, in the main wallet's accounts and in every Butler wallet's own. One duty per owner, with nothing to set. The options-trading skill files it once, as soon as any venue has an account, and never per trade.

## How it is filed

`{"recipe": "options-lifecycle@12", "movesFunds": false, "title": "Options to expiry", "triggers": [{"kind": "timer", "intervalSeconds": 900}]}`. It replaces every `options-lifecycle@11` or older duty, which watched one option each: file this one and delete those. A sold put whose owner asked to end up owning the asset is still filed as `options-put-delivery`, and its name is added to `EXCEPT` here so only that duty reports on it.

## What it does

| When | The owner gets |
| --- | --- |
| every run | nothing: it reads what each account holds and remembers each option's size and what it cost or brought in (`costUsd`, fees included) |
| `HEADS_UP_HOURS` before an option's expiry, once | where the asset is on the venue's own index, and which way the option is leaning |
| after expiry, once the venue publishes the price | a sold note: what they kept, or what they agreed to buy or sell; a bought option: what it paid against what it cost, or that it expired worthless. Told from what the account last showed |
| on Rysk, once paid out | the asset or the USDC (`settled` in `/options/account`) |

**Where it looks.** `/options/account` answers for the main wallet on every venue. A Butler wallet's own Derive or Paradex account (a duty trading from its own wallet, such as `options-order-manager`) is found by the Platforms row Butler's server keeps for it (`serverKept`), matched to the wallet by address in `/wallets`, and read with `walletId` and `venue`. Its notes name that wallet.

## What it will not do

- **Spend anything.** It runs no command and gets no pocket.
- **Say "you now own" after an assigned put.** Derive and Paradex settle in cash: the owner holds the loss in USDC, not the asset.
- **Guess a settlement.** No price (or Rysk payout) yet: it waits, saying so once past 6 hours.
- **Report a close.** A position gone before expiry on two reads in a row is dropped quietly; the close had its own note. One empty read, or an account that cannot be read, changes nothing.
- **Finish.** With nothing held it idles, and picks up the next option by itself.
- **Watch what it never saw.** An option opened and closed, or expired, between two runs is not reported.

## Settings

| Name | Unit | Means |
| --- | --- | --- |
| `HEADS_UP_HOURS` | hours, default `24` | how long before expiry each heads-up is sent |
| `EXCEPT` | list of option names, default none | options another duty reports on (`options-put-delivery`) |

## Trigger

`{"kind": "timer", "intervalSeconds": 900}`. Settlement is usually published within minutes of expiry, so a 15-minute timer reports it within the half hour.

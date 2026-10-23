# Changelog

## 8

- **Rysk.** `VENUE` `rysk`, sold puts only, named as Rysk's fields (`SOL-30OCT26-95-P`,
  `HYPE-6NOV26-56.5-P`); every read adds `venue=rysk`. Rysk settles **physically** and,
  near the strike, the maker chooses whether to exercise, so the outcome is what Rysk
  paid out - the asset or the USDC - from `/options/account`'s `settled` (bevo-server's
  Rysk venue), never inferred from the price; the duty waits for it as for a missing
  price. No delivery buy (`DELIVER_ASSET` stops a Rysk duty) and no early-close check:
  a Rysk put cannot be bought back. Supersedes `options-lifecycle@7`.

## 7

- **Paradex.** A `VENUE` setting, `derive` (the default) or `paradex`. On Paradex it reads
  Paradex's names (`ETH-USD-30OCT26-2450-P`), adds `venue=paradex` to its account and
  ticker reads, reads the settlement by the option itself (`instrument`; Paradex keys it
  by market), and names Paradex in every sentence the owner reads. A Derive duty reads
  exactly what it read before. Supersedes `options-lifecycle@6`.

## 6

- Reports a status line for the owner's Duties row, which read "nothing yet": "Settles in 3
  days · next check 9am", then "Waiting for settlement", "Settled at $64,210" or "Closed
  before expiry". `recipe.json` `status` words each state. Supersedes `options-lifecycle@5`.
- Maintained in `butler-skill-yield-notes` under `templates/options-lifecycle/`, beside the
  options-trading skill that files it; `butler-skill-options-lifecycle` is deprecated. The
  README files it as `@6`, and the test fake records `bevo.status()`.

## 5

- Checks `/options/account` every tick until expiry, not only at the heads-up, so an
  option sold back or bought back ends the duty within half an hour even when the
  skill forgot to delete it. Seen live: a sell-back filled and the duty kept running.
  It also closes a gap: an option closed after the heads-up used to run on to
  settlement and be reported as if still held. Two "not held" reads in a row are
  needed, so one empty read never costs a holder their heads-up; an unreadable account
  still never ends a duty. Supersedes @1 to @4; a duty already filed keeps its own
  `duty.py`.

## 4

- Any asset Derive lists options on. The heads-up reads Derive's own index for the
  option (`/options/ticker`), the price it settles against, instead of a DEX price
  for a pinned Base token. `TOKEN_ID` is no longer required: it is filed only with
  `DELIVER_ASSET`, for the delivery buy, and `DELIVER_ASSET` without it stops the
  duty with a clear message. Supersedes @1, @2 and @3.

## 3

- Watches bought options too: `PRODUCT` `long_call` / `long_put`, with
  `PREMIUM_USD` the total cost. The heads-up says whether it is in the money and
  what it would pay; the outcome reports Derive's payout against the cost, or
  that it expired worthless and the cost is lost. No delivery buy for a bought
  option.
- An option closed before expiry finishes the duty quietly at the heads-up,
  either way: a bought option sold back, or a sold note bought back (checked
  against `/options/account`).

## 2

- The underlying is pinned at filing in the new required `TOKEN_ID`
  (`native:<chainId>` or `<address>:<chainId>`), replacing `CHAIN_ID`. The
  heads-up prices exactly that pin with `/token-stats` (`/token-price` is
  retired, and v1 called it with `symbol`, got a 400 and never sent a heads-up);
  an empty price read skips the tick.
- The delivery buy uses the `acp trade` grammar bevo-server parses
  (`--token-in usdc --amount-in <usd> --token-out <asset>`), spending SIZE x the
  settlement price, of the `TOKEN_ID` token on its own chain. v1's
  `acp trade buy … --amount` was unparseable.
- `acp` answers are read the way copytrade reads them: `executed`, `asked`/`ok`,
  `unrecognized`; an unreadable answer is unknown, checked with `exec_status`,
  never retried.
- Notes tell and never ask: a duty cannot hear a reply. The outcome is the
  duty's last word through `bevo.done()`; failed reads go to `bevo.fail()`.
- `UNDERLYING` is cross-checked against `INSTRUMENT`.
- The settlement read is the options rail (`/options/settlement`) on Derive v3.
- README rewritten in the hub's template format; tests and scenario fixtures added.

## 1

- First release. Watches one yield note: heads-up before expiry, outcome at
  settlement, optional post-settlement purchase of the asset.
- An assigned put is reported as "you agreed to buy", not "you have bought":
  Derive settles in cash, so the owner owns nothing until the delivery buy fills.
- Expiries parsed as 08:00 UTC, so a container in a DST zone cannot call
  settlement an hour early.

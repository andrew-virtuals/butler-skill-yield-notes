# Changelog

## 5

- **Cash is what can be spent.** A resting order's line now carries the cash it holds back
  as its value (a buy's limit x what is left, a put sale's strike x what is left; a call
  sale holds the asset, so none), and the row's Cash line is the account's USDC less those
  values. Seen on staging: Cash read $22.69 with a 2 ETH bid holding $20 of it, so $2.69 was
  spendable. The lines still add up to the account's worth. Carried-over lines (a read
  that cannot see orders) are subtracted the same way, so nothing is counted twice. The
  order's line and its value are Butler's server's own (`platformLine`).
- Supersedes `options-account@4`: SKILL.md step 9 updates an older or forked duty in place.

## 4

- **Resting orders are listed.** Each open order is its account row's last line, after the
  cash and positions: "Buying 0.95 ETH 2,600 call", status `Resting`, with its limit, what
  has filled and what it holds back. The line has no value of its own: what it holds back is
  still in the Cash line and the account's worth. Seen on staging: a $9.50 resting bid on
  Derive appeared nowhere on its row. The line is the one Butler's server builds
  (`platformLine` on each open order in the account read), so the duty and the server
  write it word for word. It refreshes every check: an order that filled or was cancelled
  drops off, and a fill shows as the position it became. A read that cannot see orders
  (`ordersUnread`, Derive's public read) keeps the lines the row already shows rather than
  wiping them.
- Supersedes `options-account@3`. A duty on `@1`, `@2` or `@3`, or a fork of one, is updated
  in place (`duty_update {"recipe": "options-account@4"}`, SKILL.md step 9).

## 3

- **A position with no mark is listed.** Rysk marks no position (`valueUsd: null`), so
  every Rysk put was left off its row. It is now listed with no value, since the venue's
  `worthUsd` already counts it at what it would settle to, and its details give the
  premium received (`costUsd`, "Paid" for a bought one) and, for a sold put, the
  collateral. An expired one not yet settled reads "Awaiting settlement". Seen on
  mainnet: an agent forked `@2` to list the premium as the value, which the app showed as
  "−$2.15", owed, for a premium the owner had been paid.
- **A venue that holds its own cash lists it.** With `cashLine` on its entry (Paradex),
  the row's first line is `Cash`, the account's `usdc`, as a Derive subaccount's row
  already was. Seen on mainnet: a Paradex row read $9.26 over a single $7.30 call, and
  the $1.96 free to trade or withdraw appeared nowhere. Rysk lists none: its USDC is the
  owner's own wallet, which the Tokens tab already counts. Butler's server writes the
  same line when it rewrites the row after an options card.
- Supersedes `options-account@2`. A duty on `@1` or `@2`, or a fork of one, is updated in
  place (`duty_update {"recipe": "options-account@3"}`, SKILL.md step 9).

## 2

- **One row per subaccount.** A venue whose account is split into subaccounts
  (`account.accounts`: Derive's risk universes) gets one row per subaccount, keyed by its
  name (`PRIME`, `RWA`), at the subaccount's own `worthUsd`, listing its cash first
  (`Cash`, its `usdc`) and then its positions. Before, every subaccount's positions were
  merged into one row, so the wallet could not say which account held what or how much
  cash each had. A venue with one account (Paradex, Rysk) keeps its one row.
- **The rows a split replaces are removed.** Once every subaccount row is saved, the
  venue's other rows on the same site (the single row keyed by the wallet, a subaccount
  that is gone) are removed with `bevo-platforms remove`, so the wallet total never counts
  an account twice. Nothing is removed on a check where any subaccount row was not saved,
  had no worth, or the rows could not be listed.
- A sold option keeps its negative value (owed, not held). The server refused any
  negative `valueUsd` until it accepted signed position values, and every write of an
  account holding a sold note failed with it, leaving the row at its last value.
- Supersedes `options-account@1`: a duty filed from it is updated in place
  (`duty_update {"recipe": "options-account@2"}`, SKILL.md step 9).

## 1

- First release. One duty per owner keeps a row on the wallet page's Platforms tab for
  every options venue bevo-server trades (Derive and Paradex today): one bare
  `/options/account` read, one row per venue whose account exists, keyed by the venue's
  `site` and the owner's wallet, named by its `name`, at its `worthUsd`, listing each
  open position. No settings: a venue the server adds appears on the next check.
- The worth is the venue's own figure, as it stands: no venue's accounting lives here.
- A venue that fails to read, or reads with no worth, keeps its row at the last good
  value while the others are written. A 0 is only ever an account that read fine and
  holds nothing.
- One note: a deposit landing, only on a venue whose deposits are credited after their
  card has closed (`depositsLandLater`, Derive's bridge). Supersedes `derive-account@1`
  (`"supersedes"`), so the registry resolves that ref here.
- Read-only: no `acp` call, never `bevo.fail()`.

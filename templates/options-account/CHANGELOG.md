# Changelog

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

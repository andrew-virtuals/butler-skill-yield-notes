# Changelog

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
  card has closed (`depositsLandLater`, Derive's bridge). Supersedes `derive-account`,
  which the skill no longer files.
- Read-only: no `acp` call, never `bevo.fail()`.

# Changelog

## 1

- First release. Keeps one row on the wallet page's Platforms tab at what the owner's
  account on one options venue (`VENUE`: `paradex`) is worth: USDC, plus bought
  positions at mark, less sold ones at what buying them back costs, plus any collateral
  asset at the venue's index. The row's name and site come from bevo-server's account
  read, keyed by the venue's site and the owner's wallet, and it lists each open
  position.
- A failed or partly priced read writes nothing, so the row keeps its last good value.
  A 0 is only ever an account that read fine and holds nothing.
- Read-only and silent: no notes, no `acp` call, never `bevo.fail()`.

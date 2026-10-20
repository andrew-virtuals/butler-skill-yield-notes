# Changelog

## 1

- First release. Keeps one row on the wallet page's Platforms tab at what the owner's
  Derive options account is worth: USDC, plus bought positions at mark, less sold ones
  at what buying them back costs, plus collateral assets at Derive's index. The row is
  keyed by the owner's wallet.
- A failed or partly priced read writes nothing, so the row keeps its last good value.
  A 0 is only ever an account that read fine and holds nothing.
- One note, a deposit landing: USDC up by $1 or more with the same positions, and no
  position changed in the last hour, so a settlement's cash is not taken for a deposit.
- Read-only: imports only `bevo`, `time` and `random`, and makes no `acp` call. Never
  calls `bevo.fail()` because Derive is out of reach.

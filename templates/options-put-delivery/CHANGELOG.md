# Changelog

## 1

- **Split out of `options-lifecycle@9`.** The same watch for one sold Derive or Paradex
  put (heads-up, outcome), with the delivery buy always on: after an assigned put it buys
  SIZE x the settlement price of the `TOKEN_ID` token, keyed `note:<duty>:deliver`, never
  retried. Filed only when the owner asked, before the open, to end up owning the asset,
  so it is the only options duty that asks for a pocket, sized from `COLLATERAL_USD`.
- **Never buys for a put missing at the last check before expiry.** One empty account
  read, then expiry, used to buy anyway: a put bought back in the final 15 minutes
  would have been "delivered".

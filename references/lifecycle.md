# Keeping the lifecycle duty in step

SKILL.md step 7 files one `options-lifecycle` duty per open option, and deletes it after
a confirmed close. Two cases need more.

## Part of it is still open

A close that filled only part, or that the owner sized under what they hold, leaves a
position. After the `duty_delete`, file the duty again as in step 7, with:

- `SIZE`: what `positions` shows now, positive (a sold put's size is negative there).
- `PREMIUM_USD` and `COLLATERAL_USD`: the first duty's figures scaled to that size.

Never file one for an unknown or failed trade.

## A second options duty in one chat

A `duty_create` for another options duty in the same chat needs
`"alongside": [<this chat's earlier ones>]`, naming each earlier options duty filed here.
The `options-account` duty of step 9 needs none.

## Say to the owner

"You sold back 0.1 of your 0.3 ETH call; I'm still watching the 0.2 ETH left to expiry."

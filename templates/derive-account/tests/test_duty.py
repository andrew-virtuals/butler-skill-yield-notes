"""duty.py run against scripted reads and clocks.

    python3 -m unittest discover -s tests -v
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_bevo import WALLET, BevoError, account, every, position, run  # noqa: E402

SOURCE = (Path(__file__).resolve().parent.parent / "duty.py").read_text()

CALL = "ETH-20261030-3000-C"
PUT = "ETH-20261030-2450-P"
LONG = "BTC-20261030-90000-C"


def ticker(index):
    return {"instrument": CALL, "index": index, "mark": "12.3", "bid": "11.9", "ask": "12.8"}


class Value(unittest.TestCase):
    def test_cash_plus_bought_less_sold_plus_collateral_at_index(self):
        body = account("1000.50", [position(LONG, 0.01, 40.25), position(PUT, -0.1, 2.29),
                                   position(CALL, -0.5, 10)],
                       assets={"ETH": {"held": 0.5, "lockedForCalls": 0.5}})
        fake = run([0], {"/options/account": body, "/options/ticker": ticker("2600")})
        # 1000.50 + 40.25 - 2.29 - 10 + 0.5 x 2600
        self.assertEqual(fake.rows, [{"site": "https://www.derive.xyz", "name": "Derive",
                                      "usd": 2328.46, "account": WALLET}])
        # Any ETH option's ticker carries the ETH index; it is read once, never for BTC.
        tickers = [q["instrument"] for path, q in fake.read_calls if path == "/options/ticker"]
        self.assertEqual(len(tickers), 1)
        self.assertTrue(tickers[0].startswith("ETH-"))
        self.assertEqual(fake.statuses, [("ok", {"value": 2328.46, "positions": 3})])

    def test_an_empty_account_that_reads_fine_is_a_real_zero(self):
        fake = run([0], {"/options/account": account("0")})
        self.assertEqual(fake.rows[0]["usd"], 0)
        self.assertEqual(fake.statuses, [("ok", {"value": 0, "positions": 0})])

    def test_checks_at_start_and_on_every_tick(self):
        fake = run(every(10, 3), {"/options/account": account("5")})
        self.assertEqual(len(fake.rows), 3)


class NothingWritten(unittest.TestCase):
    def assert_untouched(self, fake, state):
        self.assertEqual(fake.rows, [])
        self.assertEqual(fake.notes, [])
        self.assertEqual(fake.fails, [])
        self.assertEqual([s for s, _ in fake.statuses], [state])

    def test_an_unreadable_account(self):
        fake = run([0], {"/options/account": BevoError("503 OPTIONS_VENUE_UNAVAILABLE")})
        self.assert_untouched(fake, "unreadable")

    def test_the_signer_off(self):
        body = dict(account(), account=None, signerReady=False)
        self.assert_untouched(run([0], {"/options/account": body}), "signer_off")

    def test_no_account_yet(self):
        fake = run([0], {"/options/account": account(exists=False)})
        self.assert_untouched(fake, "no_account")

    def test_a_position_without_a_mark(self):
        body = account("100", [position(PUT, -0.1, None)])
        self.assert_untouched(run([0], {"/options/account": body}), "unpriced")

    def test_a_collateral_asset_whose_index_cannot_be_read(self):
        body = account("100", [position(CALL, -0.5, 10)], assets={"ETH": {"held": 0.5}})
        fake = run([0], {"/options/account": body, "/options/ticker": BevoError("503")})
        self.assert_untouched(fake, "unpriced")

    def test_a_collateral_asset_with_an_empty_index(self):
        body = account("100", [position(CALL, -0.5, 10)], assets={"ETH": {"held": 0.5}})
        fake = run([0], {"/options/account": body, "/options/ticker": ticker(None)})
        self.assert_untouched(fake, "unpriced")

    def test_a_total_below_zero(self):
        body = account("1", [position(PUT, -0.1, 50)])
        self.assert_untouched(run([0], {"/options/account": body}), "unpriced")

    def test_a_malformed_answer_is_logged_and_the_next_tick_still_runs(self):
        fake = run(every(10, 2), {"/options/account": [account("not a number"), account("7")]})
        self.assertEqual(fake.fails, [])
        self.assertTrue(any(line.startswith("check skipped") for line in fake.logs))
        self.assertEqual([row["usd"] for row in fake.rows], [7])


class Deposits(unittest.TestCase):
    HELD = [position(PUT, -0.1, 2.29)]

    def test_a_deposit_is_noted_once_with_what_the_account_is_worth(self):
        fake = run(every(10, 3), {"/options/account": [account("100", self.HELD), account("600", self.HELD)]})
        self.assertEqual(fake.notes, ["Your Derive deposit landed: $500.00 USDC credited. "
                                      "The account is worth $597.71 now."])
        self.assertEqual(fake.pushes, ["Derive deposit credited"])
        self.assertEqual([s for s, _ in fake.statuses], ["ok", "credited", "ok"])
        self.assertEqual(fake.statuses[1][1]["credit"], 500)

    def test_the_first_check_has_nothing_to_compare_with(self):
        fake = run([0], {"/options/account": account("600")})
        self.assertEqual(fake.notes, [])

    def test_the_deposit_that_creates_the_account(self):
        fake = run(every(10, 2), {"/options/account": [account(exists=False), account("250")]})
        self.assertEqual(len(fake.notes), 1)
        self.assertIn("$250.00 USDC credited", fake.notes[0])

    def test_a_rise_under_a_dollar_is_not_a_deposit(self):
        fake = run(every(10, 2), {"/options/account": [account("100"), account("100.99")]})
        self.assertEqual(fake.notes, [])

    def test_a_withdrawal_says_nothing(self):
        fake = run(every(10, 2), {"/options/account": [account("600"), account("100")]})
        self.assertEqual(fake.notes, [])

    def test_a_settlement_paying_cash_is_not_a_deposit_for_an_hour(self):
        # The bought call settles: the position goes, its payout lands, and more
        # of it is credited on the next check.
        reads = [account("100", [position(LONG, 0.01, 40)]), account("140"), account("160"),
                 account("160"), account("160"), account("160"), account("160"), account("700")]
        fake = run(every(10, 8), {"/options/account": reads})
        self.assertEqual(len(fake.notes), 1)
        self.assertIn("$540.00 USDC credited", fake.notes[0])

    def test_a_deposit_spent_on_an_open_in_the_same_check_is_not_noted(self):
        reads = [account("100"), account("580", self.HELD)]
        fake = run(every(10, 2), {"/options/account": reads})
        self.assertEqual(fake.notes, [])

    def test_a_deposit_seen_during_an_unpriced_check_is_noted_once_priced(self):
        reads = [account("100", self.HELD), account("600", [position(PUT, -0.1, None)]),
                 account("600", self.HELD)]
        fake = run(every(10, 3), {"/options/account": reads})
        self.assertEqual(len(fake.notes), 1)
        self.assertIn("$500.00 USDC credited", fake.notes[0])

    def test_an_odd_no_account_read_keeps_the_baseline(self):
        reads = [account("600"), account(exists=False), account("600")]
        fake = run(every(10, 3), {"/options/account": reads})
        self.assertEqual(fake.notes, [])


class Source(unittest.TestCase):
    def test_imports_only_bevo_time_and_random(self):
        imported = set()
        for node in ast.walk(ast.parse(SOURCE)):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(imported, {"bevo", "time", "random"})

    def test_never_fails_and_never_runs_acp(self):
        called = {node.func.attr for node in ast.walk(ast.parse(SOURCE))
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn("fail", called)
        self.assertNotIn('"acp"', SOURCE)


if __name__ == "__main__":
    unittest.main()

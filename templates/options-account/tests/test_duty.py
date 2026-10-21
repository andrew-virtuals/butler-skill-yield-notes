"""duty.py run against scripted reads and clocks.

    python3 -m unittest discover -s tests -v
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_bevo import SITE, WALLET, BevoError, account, every, position, run  # noqa: E402

SOURCE = (Path(__file__).resolve().parent.parent / "duty.py").read_text()

CALL = "ETH-USD-23OCT26-2550-C"
PUT = "ETH-USD-23OCT26-2300-P"
HYPE = "HYPE-USD-6NOV26-72_5-P"


class Value(unittest.TestCase):
    def test_cash_plus_bought_less_sold_with_each_position_listed(self):
        body = account("100.50", [position(CALL, 0.1, 0.57, pnl=-0.13), position(PUT, -0.2, 1.2),
                                  position(HYPE, -1, 0.8)])
        fake = run([0], {"/options/account": body})
        row = fake.rows[0]
        self.assertEqual({k: row[k] for k in ("site", "name", "usd", "account")},
                         {"site": SITE, "name": "Paradex", "usd": 99.07, "account": WALLET})
        self.assertEqual([p["title"] for p in row["positions"]],
                         ["Bought 0.1 ETH 2,550 call", "Sold 0.2 ETH 2,300 put", "Sold 1 HYPE 72.5 put"])
        self.assertEqual([p["valueUsd"] for p in row["positions"]], [0.57, -1.2, -0.8])
        self.assertEqual(row["positions"][0]["details"],
                         [{"label": "Expires", "value": "in 2 days"}, {"label": "Up/down", "value": "$-0.13"}])
        self.assertEqual(fake.statuses, [("ok", {"value": 99.07, "positions": 3})])

    def test_every_read_names_the_venue(self):
        fake = run([0], {"/options/account": account("5")})
        self.assertEqual(fake.read_calls, [("/options/account", {"venue": "paradex"})])

    def test_an_empty_account_that_reads_fine_is_a_real_zero_with_no_positions(self):
        fake = run([0], {"/options/account": account("0")})
        self.assertEqual((fake.rows[0]["usd"], fake.rows[0]["positions"]), (0, []))

    def test_a_collateral_asset_is_priced_at_the_venues_index(self):
        body = account("10", [position(CALL, -0.5, 10)], assets={"ETH": {"held": 0.5}})
        ticker = lambda q: {"instrument": q["instrument"], "index": "2400"}  # noqa: E731
        fake = run([0], {"/options/account": body, "/options/ticker": ticker})
        self.assertEqual(fake.rows[0]["usd"], 1200)
        self.assertIn(("/options/ticker", {"venue": "paradex", "instrument": CALL}), fake.read_calls)

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

    def test_an_answer_without_a_site(self):
        body = dict(account("5"), site=None)
        self.assert_untouched(run([0], {"/options/account": body}), "unreadable")

    def test_the_signer_off(self):
        body = dict(account(), account=None, signerReady=False)
        self.assert_untouched(run([0], {"/options/account": body}), "signer_off")

    def test_no_account_yet(self):
        self.assert_untouched(run([0], {"/options/account": account(exists=False)}), "no_account")

    def test_a_position_without_a_mark(self):
        body = account("100", [position(PUT, -0.1, None)])
        self.assert_untouched(run([0], {"/options/account": body}), "unpriced")

    def test_a_total_below_zero(self):
        body = account("1", [position(PUT, -0.1, 50)])
        self.assert_untouched(run([0], {"/options/account": body}), "unpriced")

    def test_no_venue_reads_nothing(self):
        fake = run(every(10, 2), {"/options/account": account("5")}, params={})
        self.assertEqual(fake.read_calls, [])
        self.assert_untouched(fake, "unreadable")

    def test_a_malformed_answer_is_logged_and_the_next_tick_still_runs(self):
        fake = run(every(10, 2), {"/options/account": [account("not a number"), account("7")]})
        self.assertEqual(fake.fails, [])
        self.assertTrue(any(line.startswith("check skipped") for line in fake.logs))
        self.assertEqual([row["usd"] for row in fake.rows], [7])


class Source(unittest.TestCase):
    def test_imports_only_what_a_reader_needs(self):
        imported = set()
        for node in ast.walk(ast.parse(SOURCE)):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(imported, {"bevo", "json", "os", "random", "time"})

    def test_never_fails_never_notifies_and_never_runs_acp(self):
        called = {node.func.attr for node in ast.walk(ast.parse(SOURCE))
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn("fail", called)
        self.assertNotIn("notify", called)
        self.assertNotIn('"acp"', SOURCE)


if __name__ == "__main__":
    unittest.main()

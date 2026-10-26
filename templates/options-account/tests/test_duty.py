"""duty.py run against scripted reads and clocks.

    python3 -m unittest discover -s tests -v
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_bevo import (DERIVE, PARADEX, WALLET, BevoError, accounts, derive, every,  # noqa: E402
                       paradex, platform, position, run, subaccount, venue)

SOURCE = (Path(__file__).resolve().parent.parent / "duty.py").read_text()

CALL = "ETH-USD-6NOV26-2500-C"
PUT = "ETH-USD-23OCT26-2300-P"
DERIVE_CALL = "ETH-20261030-2550-C"


def rows(fake):
    return [(row["site"], row["name"], row["usd"]) for row in fake.rows]


class EveryVenue(unittest.TestCase):
    # Mainnet, andrew4 (2026-10-22): Derive worth 4.54, Paradex 13.93, a call open on each.
    def test_one_row_per_venue_at_its_own_worth_with_its_positions(self):
        body = accounts(derive("1.45", 4.541177, [position(DERIVE_CALL, 0.17, 3.1)]),
                        paradex("8.11", 13.932716, [position(CALL, 0.1, 5.82, pnl=0.07), position(PUT, -0.2, 1.2)]))
        fake = run([0], {"/options/account": body})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 4.54), (PARADEX, "Paradex", 13.93)])
        self.assertEqual({row["account"] for row in fake.rows}, {WALLET})
        self.assertEqual([p["title"] for p in fake.rows[1]["positions"]],
                         ["Cash", "Bought 0.1 ETH 2,500 call", "Sold 0.2 ETH 2,300 put"])
        self.assertEqual([p["valueUsd"] for p in fake.rows[1]["positions"]], [8.11, 5.82, -1.2])
        self.assertEqual(fake.rows[1]["positions"][1]["details"],
                         [{"label": "Expires", "value": "in 2 days"}, {"label": "Up/down", "value": "$0.07"}])
        self.assertEqual(fake.statuses, [("ok", {"value": 18.47, "positions": 3})])

    def test_one_bare_read_answers_for_every_venue(self):
        fake = run([0], {"/options/account": accounts(derive("5", 5), paradex("5", 5))})
        self.assertEqual(fake.read_calls, [("/options/account", {})])

    def test_a_venue_the_server_adds_is_written_with_nothing_refiled(self):
        later = venue("aevo", "Aevo", "https://www.aevo.xyz", "3", 3)
        fake = run([0], {"/options/account": accounts(derive("5", 5), later)})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 5), ("https://www.aevo.xyz", "Aevo", 3)])

    def test_only_a_venue_that_exists_gets_a_row(self):
        fake = run([0], {"/options/account": accounts(derive(exists=False), paradex("7", 7))})
        self.assertEqual(rows(fake), [(PARADEX, "Paradex", 7)])

    def test_an_empty_account_that_reads_fine_is_a_real_zero(self):
        fake = run([0], {"/options/account": accounts(paradex("0", 0))})
        self.assertEqual((fake.rows[0]["usd"], fake.rows[0]["positions"]),
                         (0, [{"title": "Cash", "valueUsd": 0}]))

    # Mainnet (2026-10-26): $9.26 on Paradex, $7.30 of it a call, so $1.96 free.
    def test_a_venue_holding_its_cash_lists_it_first_and_counts_it_as_no_position(self):
        fake = run([0], {"/options/account": accounts(paradex("1.964", 9.264, [position(CALL, 0.01, 7.3)]))})
        self.assertEqual([(p["title"], p["valueUsd"]) for p in fake.rows[0]["positions"]],
                         [("Cash", 1.96), ("Bought 0.01 ETH 2,500 call", 7.3)])
        self.assertEqual(fake.statuses, [("ok", {"value": 9.26, "positions": 1})])

    def test_cash_stays_inside_the_twenty_line_limit(self):
        many = [position("ETH-USD-6NOV26-%d-C" % (2000 + i), 0.1, 1) for i in range(25)]
        line = run([0], {"/options/account": accounts(paradex("3", 28, many))}).rows[0]["positions"]
        self.assertEqual((len(line), line[0]["title"]), (20, "Cash"))

    def test_checks_at_start_and_on_every_tick(self):
        fake = run(every(10, 3), {"/options/account": accounts(paradex("5", 5))})
        self.assertEqual(len(fake.rows), 3)


RYSK = "https://app.rysk.finance"


def sold_put(instrument="SOL-30OCT26-93-P", size=10, received=2.15, expires="in 3 days"):
    # Butler's server reads Rysk with no mark, so no value and no P&L; `costUsd` is the premium received.
    parts = instrument.split("-")
    return {"instrument": instrument, "size": -size, "underlying": parts[0], "strike": float(parts[2]),
            "type": "P", "valueUsd": None, "costUsd": received, "pnlUsd": None, "expiresIn": expires}


class Unmarked(unittest.TestCase):
    # Mainnet (2026-10-26): a sold SOL put on Rysk, which marks no position.
    def test_a_position_with_no_mark_is_listed_without_a_value(self):
        rysk = venue("rysk", "Rysk", RYSK, "0", 930, [sold_put()])
        fake = run([0], {"/options/account": accounts(rysk)})
        self.assertEqual(rows(fake), [(RYSK, "Rysk", 930)])
        self.assertEqual(fake.rows[0]["positions"], [{
            "title": "Sold 10 SOL 93 put", "subtitle": "SOL-30OCT26-93-P",
            "details": [{"label": "Expires", "value": "in 3 days"}, {"label": "Received", "value": "$2.15"},
                        {"label": "Collateral", "value": "$930.00"}]}])
        self.assertEqual(fake.statuses, [("ok", {"value": 930, "positions": 1})])

    def test_an_expired_unsettled_one_awaits_settlement(self):
        rysk = venue("rysk", "Rysk", RYSK, "0", 930, [sold_put(expires="expired")])
        line = run([0], {"/options/account": accounts(rysk)}).rows[0]["positions"][0]
        self.assertEqual(line["status"], "Awaiting settlement")
        self.assertNotIn("Expires", [d["label"] for d in line["details"]])


def split_derive(prime_worth=51.53, rwa_worth=6.58):
    # Mainnet (2026-10-26): PRIME holds ETH options, RWA a XAUT call.
    prime = subaccount("PRIME", 1, 17.02, prime_worth, [position("ETH-20261030-2700-C", 0.1, 0.13),
                                                        position("ETH-20261030-2450-P", 0.24, 34.38)])
    rwa = subaccount("RWA", 2, 0, rwa_worth, [position("XAUT-20261113-4200-C", 0.23, 6.58)])
    return derive("17.02", 58.11, subs=[prime, rwa])


class Subaccounts(unittest.TestCase):
    def test_one_row_per_subaccount_at_its_own_worth_cash_first(self):
        fake = run([0], {"/options/account": accounts(split_derive())})
        self.assertEqual([(row["account"], row["usd"]) for row in fake.rows], [("PRIME", 51.53), ("RWA", 6.58)])
        self.assertEqual({(row["site"], row["name"]) for row in fake.rows}, {(DERIVE, "Derive")})
        self.assertEqual([(p["title"], p["valueUsd"]) for p in fake.rows[0]["positions"]],
                         [("Cash", 17.02), ("Bought 0.1 ETH 2,700 call", 0.13), ("Bought 0.24 ETH 2,450 put", 34.38)])
        self.assertEqual([(p["title"], p["valueUsd"]) for p in fake.rows[1]["positions"]],
                         [("Cash", 0), ("Bought 0.23 XAUT 4,200 call", 6.58)])
        self.assertEqual(fake.statuses, [("ok", {"value": 58.11, "positions": 3})])

    def test_the_venue_row_and_a_gone_subaccount_are_retired_and_nothing_else(self):
        existing = [platform("old", DERIVE, WALLET), platform("alt", DERIVE, "ALT"),
                    platform("prime", DERIVE, "PRIME"), platform("px", PARADEX, WALLET),
                    platform("stake", "https://stake.com", "")]
        fake = run([0], {"/options/account": accounts(split_derive(), paradex("5", 5))}, platforms=existing)
        self.assertEqual(fake.removed, ["old", "alt"])

    def test_nothing_is_retired_while_a_subaccount_row_is_unsaved(self):
        fake = run([0], {"/options/account": accounts(split_derive())},
                   platforms=[platform("old", DERIVE, WALLET)], refuse={"RWA"})
        self.assertEqual(fake.removed, [])

    def test_a_subaccount_with_no_worth_keeps_every_row(self):
        fake = run([0], {"/options/account": accounts(split_derive(rwa_worth=None), paradex("5", 5))},
                   platforms=[platform("old", DERIVE, WALLET)])
        self.assertEqual(rows(fake), [(PARADEX, "Paradex", 5)])
        self.assertEqual(fake.removed, [])
        self.assertEqual(fake.statuses, [("partial", {"value": 5, "skipped": 1})])

    def test_rows_that_cannot_be_listed_are_left_and_the_check_still_reports(self):
        fake = run([0], {"/options/account": accounts(split_derive())}, platforms=BevoError("503"))
        self.assertEqual(fake.removed, [])
        self.assertTrue(any("none was retired" in line for line in fake.logs))
        self.assertEqual(fake.statuses, [("ok", {"value": 58.11, "positions": 3})])


class OneVenueMissed(unittest.TestCase):
    def test_an_unreadable_venue_keeps_its_row_and_the_rest_are_written(self):
        down = dict(paradex(), available=False, error="Paradex answered 502")
        fake = run([0], {"/options/account": accounts(derive("5", 5), down)})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 5)])
        self.assertEqual(fake.statuses, [("partial", {"value": 5, "skipped": 1})])
        self.assertTrue(any("Paradex answered 502" in line for line in fake.logs))

    def test_a_venue_with_no_worth_keeps_its_row(self):
        fake = run([0], {"/options/account": accounts(derive("5", 5), paradex("5", None))})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 5)])
        self.assertEqual(fake.statuses, [("partial", {"value": 5, "skipped": 1})])

    def test_a_venue_this_server_does_not_trade_is_left_out_quietly(self):
        off = dict(paradex(), available=False, reason="not configured on this server")
        fake = run([0], {"/options/account": accounts(derive("5", 5), off)})
        self.assertEqual(fake.statuses, [("ok", {"value": 5, "positions": 0})])


class DepositNote(unittest.TestCase):
    def test_a_rise_on_a_venue_whose_deposits_land_later_is_noted(self):
        fake = run(every(10, 2), {"/options/account": [accounts(derive("5", 5)), accounts(derive("55", 55))]})
        self.assertEqual(fake.notes, ["Your Derive deposit landed: $50.00 USDC credited. The account is worth $55.00 now."])
        self.assertEqual(fake.pushes, ["Derive deposit credited"])
        self.assertEqual(fake.statuses[-1], ("credited", {"credit": 50, "value": 55, "positions": 0}))

    def test_the_first_deposit_is_a_rise_from_zero(self):
        fake = run(every(10, 2), {"/options/account": [accounts(derive(exists=False)), accounts(derive("20", 20))]})
        self.assertEqual(len(fake.notes), 1)

    def test_a_venue_whose_card_reports_the_credit_gets_no_note(self):
        fake = run(every(10, 2), {"/options/account": [accounts(paradex("5", 5)), accounts(paradex("55", 55))]})
        self.assertEqual(fake.notes, [])

    def test_the_first_check_and_cash_from_a_close_are_not_deposits(self):
        held = [position(DERIVE_CALL, 0.17, 3.1)]
        fake = run(every(10, 3), {"/options/account": [accounts(derive("5", 8, held)), accounts(derive("9", 9)),
                                                       accounts(derive("9", 9))]})
        self.assertEqual(fake.notes, [])


class NothingWritten(unittest.TestCase):
    def assert_untouched(self, fake, state):
        self.assertEqual(fake.rows, [])
        self.assertEqual(fake.notes, [])
        self.assertEqual(fake.fails, [])
        self.assertEqual([s for s, _ in fake.statuses], [state])

    def test_an_unreadable_read(self):
        fake = run([0], {"/options/account": BevoError("503 OPTIONS_VENUE_UNAVAILABLE")})
        self.assert_untouched(fake, "unreadable")

    def test_a_read_listing_no_venues(self):
        self.assert_untouched(run([0], {"/options/account": {"account": None}}), "unreadable")

    def test_a_venue_without_a_site(self):
        body = accounts(dict(paradex("5", 5), site=None))
        self.assert_untouched(run([0], {"/options/account": body}), "unreadable")

    def test_the_signer_off(self):
        body = accounts(dict(derive(), account=None), dict(paradex(), account=None))
        self.assert_untouched(run([0], {"/options/account": body}), "signer_off")

    def test_no_account_yet(self):
        body = accounts(derive(exists=False), paradex(exists=False))
        self.assert_untouched(run([0], {"/options/account": body}), "no_account")

    def test_a_worth_below_zero(self):
        self.assert_untouched(run([0], {"/options/account": accounts(paradex("1", -3))}), "unpriced")

    def test_a_malformed_answer_is_logged_and_the_next_tick_still_runs(self):
        fake = run(every(10, 2), {"/options/account": [accounts(paradex("1", "not a number")),
                                                       accounts(paradex("7", 7))]})
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
        self.assertEqual(imported, {"bevo", "random", "subprocess", "time"})

    def test_names_no_venue_and_never_fails_or_runs_acp(self):
        called = {node.func.attr for node in ast.walk(ast.parse(SOURCE))
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn("fail", called)
        self.assertNotIn('"acp"', SOURCE)
        for name in ("derive", "paradex"):
            self.assertNotIn('"%s' % name, SOURCE.lower())


if __name__ == "__main__":
    unittest.main()

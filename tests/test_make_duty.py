"""scripts/make_duty.py: the payload it prints, and what it refuses to build."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import make_duty  # noqa: E402

RULE = '''STRIKE = float(P["STRIKE"])


def trigger():
    spot = quote("minimum", "--underlying", "ETH").get("spot")
    if spot is None:
        return False, "ETH unread"
    return spot < STRIKE, "ETH at $%s" % format(spot, ",.0f")


def order():
    q = quote("quote", "--product", "cash_secured_put", "--underlying", "ETH", "--collateral", "750")
    if q.get("error") or not q.get("tradeable"):
        return None, "the quote is not tradeable"
    return ["open", "--instrument", q["instrument"], "--size", str(q["size"]), "--min-premium",
            str(q["min_premium_usd"]), "--max-collateral", str(q["collateral"]["amount"])], "sell a put"
'''


class Build(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        patch = mock.patch.dict(os.environ, {"HOME": self.home.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.rule = os.path.join(self.home.name, "rule.py")
        self.write(RULE)

    def write(self, text):
        with open(self.rule, "w", encoding="utf-8") as f:
            f.write(text)

    def run_it(self, *args):
        base = ["--name", "Sell ETH puts below $1,500", "--spec", "sell puts if ETH drops below 1500",
                "--set-aside", "1000", "--need", "750", "--rule", self.rule]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = make_duty.main(base + list(args))
        return code, (json.loads(out.getvalue()) if code == 0 else None), err.getvalue()

    def test_own_wallet_payload(self):
        code, answer, _ = self.run_it("--wallet", "own", "--wallet-label", "eth-puts", "--param", "STRIKE=1500")
        self.assertEqual(code, 0)
        duty = answer["duty_create"]
        self.assertEqual(duty["walletId"], "eth-puts")
        self.assertEqual(duty["fundUsdc"], 1020)
        self.assertNotIn("pocketUsdc", duty)
        self.assertNotIn("code", duty)
        self.assertEqual(duty["title"], "{NAME}")
        self.assertEqual(duty["triggers"], [{"kind": "timer", "intervalSeconds": 300, "untilDone": True}])
        self.assertEqual(duty["spendBasis"], {"perTrade": "NEED_USD", "times": "TIMES"})
        self.assertEqual(duty["statusTemplate"], make_duty.STATUS)
        self.assertEqual(duty["params"], {
            "NAME": "Sell ETH puts below $1,500", "VENUE": "derive", "OWN_WALLET": True,
            "ALLOCATION_USD": 1000.0, "NEED_USD": 750.0, "TIMES": 1,
            "QUOTE_PY": os.path.join(os.path.realpath(SCRIPTS), "quote.py"), "STRIKE": 1500})
        self.assertEqual(duty["codePath"], "duties/sell-eth-puts-below/duty.py")

    def test_the_saved_program_is_the_template_with_the_rule_in_it(self):
        _, answer, _ = self.run_it("--wallet", "own", "--wallet-label", "w", "--param", "STRIKE=1500")
        saved = make_duty.read(answer["saved"])
        template = make_duty.read(make_duty.PROGRAM)
        before, after = make_duty.RULE.split(template)
        self.assertTrue(saved.startswith(before))
        self.assertTrue(saved.endswith(after))
        self.assertIn('STRIKE = float(P["STRIKE"])', saved)
        self.assertNotIn("NotImplementedError", saved)
        self.assertIn('["acp", "options", *args, "--idempotency-key", key]', saved)

    def test_funding_is_the_amount_set_aside_plus_two_percent(self):
        for aside, need, fund in (("10", "9.79", 11), ("15", "10", 16), ("100", "80", 102)):
            _, answer, _ = self.run_it("--wallet", "own", "--wallet-label", "w", "--set-aside", aside,
                                       "--need", need, "--param", "STRIKE=1")
            self.assertEqual(answer["duty_create"]["fundUsdc"], fund)

    def test_main_wallet_short_on_the_venue_deposits_first(self):
        code, answer, _ = self.run_it("--wallet", "main", "--free", "50")
        self.assertEqual(code, 0)
        self.assertNotIn("duty_create", answer)
        self.assertEqual(answer["deposit_first"]["amount_usdc"], 969)

    def test_main_wallet_covered_proposes_the_amount_set_aside(self):
        _, answer, _ = self.run_it("--wallet", "main", "--free", "1000")
        duty = answer["duty_create"]
        self.assertEqual(duty["pocketUsdc"], 1000.0)
        self.assertFalse(duty["params"]["OWN_WALLET"])
        self.assertNotIn("walletId", duty)
        self.assertNotIn("fundUsdc", duty)

    def test_a_card_on_every_trade_is_a_zero_limit(self):
        _, answer, _ = self.run_it("--wallet", "main", "--free", "1000", "--card-each-trade")
        self.assertEqual(answer["duty_create"]["pocketUsdc"], 0)

    def test_a_set_time_runs_every_minute_and_paradex_is_carried(self):
        _, answer, _ = self.run_it("--wallet", "main", "--free", "1000", "--every", "60", "--venue", "paradex")
        self.assertEqual(answer["duty_create"]["triggers"][0]["intervalSeconds"], 60)
        self.assertEqual(answer["duty_create"]["params"]["VENUE"], "paradex")

    def refused(self, *args):
        code, _, err = self.run_it(*args)
        self.assertEqual(code, 2)
        return err

    def test_refusals(self):
        own = ("--wallet", "own", "--wallet-label", "w")
        self.assertIn("38 characters", self.refused(*own, "--name", "x" * 39))
        self.assertIn("more than the", self.refused(*own, "--need", "1200"))
        self.assertIn("--wallet-label", self.refused("--wallet", "own"))
        self.assertIn("minimum deposit", self.refused(*own, "--set-aside", "8", "--need", "5"))
        self.assertIn("--free", self.refused("--wallet", "main"))
        self.assertIn("set by this script", self.refused(*own, "--param", "NEED_USD=1"))
        self.assertIn("no figures", self.refused(*own, "--slug", "eth-puts-2"))

    def test_rule_refusals(self):
        own = ("--wallet", "own", "--wallet-label", "w")
        for text, why in (
            ("def trigger():\n    return True, 'x'\n", "defines no order()"),
            ("def trigger(:\n", "not valid Python"),
            (RULE + "\ndef short(a, b, c):\n    pass\n", "redefines short"),
            ("def trigger():\n    return True, 'x'\n\ndef order():\n    return ['buy'], 'x'\n", "quote("),
            (RULE + "\nimport bevo\nbevo.notify('hi')\n", "bevo.notify"),
            (RULE.replace('"sell a put"', '"python3 x"'), "python3"),
        ):
            self.write(text)
            self.assertIn(why, self.refused(*own))


if __name__ == "__main__":
    unittest.main()

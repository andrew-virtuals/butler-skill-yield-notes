"""scripts/make_duty.py: the payload it prints, and what it refuses to build."""

import contextlib
import datetime
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
        self.assertEqual(json.loads(duty["statusTemplate"]), make_duty.STATUS)
        self.assertEqual(json.loads(duty["params"]), {
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
        self.assertFalse(json.loads(duty["params"])["OWN_WALLET"])
        self.assertNotIn("walletId", duty)
        self.assertNotIn("fundUsdc", duty)

    def test_a_card_on_every_trade_is_a_zero_limit(self):
        _, answer, _ = self.run_it("--wallet", "main", "--free", "1000", "--card-each-trade")
        self.assertEqual(answer["duty_create"]["pocketUsdc"], 0)

    def test_a_set_time_runs_every_minute_and_paradex_is_carried(self):
        _, answer, _ = self.run_it("--wallet", "main", "--free", "1000", "--every", "60", "--venue", "paradex")
        self.assertEqual(answer["duty_create"]["triggers"][0]["intervalSeconds"], 60)
        self.assertEqual(json.loads(answer["duty_create"]["params"])["VENUE"], "paradex")

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
        self.assertIn("single quotes", self.refused(*own, "--name", "ETH call at ,850"))
        self.assertIn("single quotes", self.refused(*own, "--spec", "when ETH goes above ,740, buy"))

    def test_rule_refusals(self):
        own = ("--wallet", "own", "--wallet-label", "w")
        for text, why in (
            ("def trigger():\n    return True, 'x'\n", "defines no order()"),
            ("def trigger(:\n", "not valid Python"),
            (RULE + "\ndef short(a, b, c):\n    pass\n", "redefines short"),
            ("def trigger():\n    return True, 'x'\n\ndef order():\n    return ['buy'], 'x'\n", "quote("),
            (RULE + "\nimport bevo\nbevo.notify('hi')\n", "bevo.notify"),
            (RULE.replace('"sell a put"', '"python3 x"'), "python3"),
            (RULE.replace('"--min-premium",', '"--limit",'), "without --min-premium"),
            (RULE + "\nHOUR = time.gmtime().tm_hour\n", "compare timestamps"),
            (RULE.replace('"--max-collateral"', '"--min-price"').replace('"--min-premium",', '"--min-premium", "--max-collateral",'), "--min-price"),
            (RULE.replace("return spot < STRIKE,", "return {'otm': 10} if spot < STRIKE else None,"), "trigger() answered"),
            ("def trigger():\n    return True, 'x'\n\ndef order():\n    q = quote('quote')\n    return ['buy', '--instrument', 'i'], 'x'\n", "without --max-cost"),
        ):
            self.write(text)
            self.assertIn(why, self.refused(*own, "--param", "STRIKE=1500"))
        self.write(RULE + "\nHOME = 'bevo-wallet withdraw'\n")
        self.assertIn("sends the money home itself", self.refused(*own, "--param", "STRIKE=1500"))


def later(days):
    when = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=days)
    return when.isoformat(), int(datetime.datetime(when.year, when.month, when.day,
                                                   tzinfo=datetime.timezone.utc).timestamp())


class AutoRollPreset(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        patch = mock.patch.dict(os.environ, {"HOME": self.home.name})
        patch.start()
        self.addCleanup(patch.stop)

    def run_it(self, *args):
        base = ["--name", "Weekly ETH puts", "--spec", "put $5,000 on auto-roll", "--preset", "auto-roll",
                "--set-aside", "5000", "--need", "150", "--times", "14"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = make_duty.main(base + list(args))
        return code, (json.loads(out.getvalue()) if code == 0 else None), err.getvalue()

    def test_its_payload_trades_from_its_own_wallet_and_sends_everything_home(self):
        day, epoch = later(90)
        code, answer, err = self.run_it("--wallet", "own", "--wallet-label", "weekly-eth-puts",
                                        "--end-at", day, "--max-loss", "500", "--param", "UNDERLYING=ETH")
        self.assertEqual(code, 0, err)
        duty = answer["duty_create"]
        self.assertEqual(duty["fundUsdc"], 5100)
        self.assertEqual(duty["walletId"], "weekly-eth-puts")
        params = json.loads(duty["params"])
        self.assertEqual({k: params[k] for k in ("UNDERLYING", "END_AT", "MAX_LOSS_USD",
                                                 "WITHDRAW_ON_FINISH", "WALLET_LABEL", "TIMES")},
                         {"UNDERLYING": "ETH", "END_AT": epoch, "MAX_LOSS_USD": 500.0,
                          "WITHDRAW_ON_FINISH": True, "WALLET_LABEL": "weekly-eth-puts", "TIMES": 14})
        saved = make_duty.read(answer["saved"])
        self.assertIn("def put_line(name):", saved)
        self.assertIn('"--otm-pct", "%g" % BELOW, "--max-delta", "%g" % ODDS', saved)
        self.assertEqual(json.loads(duty["statusTemplate"]), make_duty.STATUS)

    def test_refusals(self):
        own = ("--wallet", "own", "--wallet-label", "w")
        day, _ = later(90)
        limits = ("--end-at", day, "--max-loss", "500")
        for args, why in (
            (("--wallet", "main", "--free", "5000", "--param", "UNDERLYING=ETH"), "own wallet only"),
            (own + ("--param", "UNDERLYING=ETH"), "needs --end-at and --max-loss"),
            (own + ("--param", "UNDERLYING=ETH", "--end-at", day), "needs --end-at and --max-loss"),
            (own + limits, "UNDERLYING"),
            (own + ("--param", "UNDERLYING=ETH", "--end-at", day, "--max-loss", "6000"), "--max-loss"),
            (own + ("--param", "UNDERLYING=ETH", "--end-at", "2020-01-01", "--max-loss", "500"), "already passed"),
            (own + ("--param", "UNDERLYING=ETH", "--end-at", "23 Feb", "--max-loss", "500"), "YYYY-MM-DD"),
            (own + limits + ("--param", "UNDERLYING=ETH", "--venue", "paradex"), "runs on Derive"),
            (own + limits + ("--param", "UNDERLYING=ETH", "--every", "60"), "runs on Derive"),
        ):
            code, _, err = self.run_it(*args)
            self.assertEqual((code, why in err), (2, True), (args, err))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_it(*own, *limits, "--param", "UNDERLYING=ETH", "--rule", "x.py")

    def test_its_trades_run_to_the_end_date_when_times_is_left_out(self):
        day, _ = later(90)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = make_duty.main(["--name", "Weekly ETH puts", "--spec", "x", "--preset", "auto-roll",
                                   "--wallet", "own", "--wallet-label", "w", "--set-aside", "5000",
                                   "--need", "150", "--end-at", day, "--max-loss", "500",
                                   "--param", "UNDERLYING=ETH"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(json.loads(json.loads(out.getvalue())["duty_create"]["params"])["TIMES"], 14)

    def test_a_main_wallet_has_no_loss_limit(self):
        rule = os.path.join(self.home.name, "rule.py")
        with open(rule, "w", encoding="utf-8") as f:
            f.write(RULE)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = make_duty.main(["--name", "ETH puts", "--spec", "x", "--set-aside", "1000", "--need", "750",
                                   "--rule", rule, "--wallet", "main", "--free", "1000",
                                   "--max-loss", "200", "--param", "STRIKE=1500"])
        self.assertEqual((code, "--max-loss is for its own wallet" in err.getvalue()), (2, True))

    def test_a_main_wallet_rule_cannot_send_money_home(self):
        rule = os.path.join(self.home.name, "rule.py")
        with open(rule, "w", encoding="utf-8") as f:
            f.write(RULE)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = make_duty.main(["--name", "ETH puts", "--spec", "x", "--set-aside", "1000", "--need", "750",
                                   "--rule", rule, "--wallet", "main", "--free", "1000",
                                   "--withdraw-on-finish", "--param", "STRIKE=1500"])
        self.assertEqual((code, "its own wallet" in err.getvalue()), (2, True))


class AutoRollStrike(unittest.TestCase):
    """quote.py's --otm-pct with --max-delta: the strike nearest spot at least that far out of
    the money, with a small enough delta and a bid."""

    def chain(self, rows):
        insts = [{"instrument_name": "ETH-20261204-%d-P" % k, "option_details": {"strike": k}}
                 for k, _, _ in rows]
        tickers = {"ETH-20261204-%d-P" % k: {"b": b, "option_pricing": {"d": -d}} for k, d, b in rows}
        return insts, tickers

    def test_the_strike_it_picks(self):
        import quote
        insts, tickers = self.chain([(1400, 0.07, 2.0), (1450, 0.10, 0), (1500, 0.137, 15.0),
                                     (1550, 0.18, 21.0), (1600, 0.24, 31.0)])
        pick = quote.strike_for(insts, tickers, "P", 1731.0, 8.0, None, None, 0.15)
        self.assertEqual(pick["option_details"]["strike"], 1500)  # 1550: delta too big; 1600: too near
        pick = quote.strike_for(insts, tickers, "P", 1731.0, 8.0, None, None, 0.12)
        self.assertEqual(pick["option_details"]["strike"], 1400)  # 1450 has no bid
        with self.assertRaises(quote.VenueError):
            quote.strike_for(insts, tickers, "P", 1731.0, 30.0, None, None, 0.15)

    def test_an_unread_delta_is_skipped_never_read_as_zero(self):
        import quote
        insts, tickers = self.chain([(1500, 0.137, 15.0), (1550, 0.18, 21.0), (1580, 0.2, 25.0)])
        for unread in ("NaN", "", None):
            tickers["ETH-20261204-1580-P"]["option_pricing"]["d"] = unread
            pick = quote.strike_for(insts, tickers, "P", 1731.0, 8.0, None, None, 0.15)
            self.assertEqual(pick["option_details"]["strike"], 1500, unread)
        del tickers["ETH-20261204-1580-P"]["option_pricing"]
        self.assertEqual(quote.strike_for(insts, tickers, "P", 1731.0, 8.0, None, None, 0.15)
                         ["option_details"]["strike"], 1500)


if __name__ == "__main__":
    unittest.main()

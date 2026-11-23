"""`scripts/quote.py`: the Virtuals platform fee in every Derive quote, read from the account, offline."""
import contextlib
import io
import json
import pathlib
import subprocess
import sys
import types
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "quote.py"

ETH_CALL = "ETH-20261204-1900-C"
INST = {
    "instrument_name": ETH_CALL, "is_active": True,
    "option_details": {"strike": "1900", "expiry": 4_000_000_000, "option_type": "C"},
    "amount_step": "0.01", "minimum_amount": "0.01",
    "base_fee": "0.5", "taker_fee_rate": "0.0003", "mark_price_fee_rate_cap": "0.125",
}
TICKER = {"b": "48", "B": "10", "a": "50", "A": "10", "M": "49", "I": "2000",
          "option_pricing": {"bi": "0.60", "ai": "0.62", "i": "0.61", "d": "0.5"}}


def account(body=None, code=0, stderr="", raises=None):
    """A stand-in for `acp options account --venue derive --json`, recording each call."""
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if raises:
            raise raises
        out = body if isinstance(body, str) else json.dumps(body or {})
        return subprocess.CompletedProcess(argv, code, stdout=out, stderr=stderr)
    return types.SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired), calls


def helper(acp):
    mod = types.ModuleType("quote")
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), mod.__dict__)
    mod.active_options = lambda cur, t: [INST]
    mod.tickers_for = lambda cur, expiry: {ETH_CALL: TICKER}
    mod.time = types.SimpleNamespace(time=lambda: 3_990_000_000)
    mod.subprocess = acp
    return mod


def run(h, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", ["quote.py", *argv]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            h.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
        except Exception as exc:  # noqa: BLE001 - as __main__ reports it
            err.write("error: %s\n" % exc)
            code = 1
    return code, out.getvalue(), err.getvalue()


CLOSE = ("quote", "--side", "close", "--instrument", ETH_CALL, "--size", "1")


class PlatformFeeTest(unittest.TestCase):
    def quote(self, rate_body, *argv):
        acp, calls = account(rate_body)
        code, out, err = run(helper(acp), "quote", *argv)
        self.assertEqual(code, 0, err)
        return json.loads(out), calls

    def test_the_rate_comes_from_the_derive_account(self):
        q, calls = self.quote({"platformFeeRate": 0.005}, *CLOSE[1:])
        self.assertEqual(calls, [["acp", "options", "account", "--venue", "derive", "--json"]])
        self.assertEqual((q["fee_usd"], q["venue_fee_usd"], q["platform_fee_usd"]), (1.34, 1.1, 0.24))
        self.assertEqual(q["net_proceeds_usd"], 46.66)  # 48 - 1.10 - 0.24

    def test_zero_is_derives_fee_alone(self):
        q, _ = self.quote({"platformFeeRate": 0}, *CLOSE[1:])
        # 0.5 + min(0.0003 x 2000, 0.125 x 49) = 1.10
        self.assertEqual((q["fee_usd"], q["venue_fee_usd"], q["platform_fee_usd"]), (1.1, 1.1, 0))
        self.assertEqual(q["net_proceeds_usd"], 46.9)

    def test_a_server_too_old_to_report_it_charges_half_a_percent(self):
        q, _ = self.quote({"account": {"exists": True}}, *CLOSE[1:])
        self.assertEqual(q["platform_fee_usd"], 0.24)

    def test_an_unreadable_account_stops_the_quote(self):
        for acp in (account(code=4, stderr="[options] could not read the derive account (503)")[0],
                    account(raises=FileNotFoundError("acp"))[0],
                    account(body="<html>")[0],
                    account({"platformFeeRate": 0.5})[0],
                    account({"platformFeeRate": "0.005"})[0]):
            code, out, err = run(helper(acp), *CLOSE)
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("could not read the Virtuals platform fee", err)

    def test_every_total_carries_it(self):
        back, _ = self.quote({"platformFeeRate": 0.005}, "--side", "buyback", "--instrument", ETH_CALL,
                             "--size", "1", "--premium-received", "60")
        self.assertEqual((back["fee_usd"], back["platform_fee_usd"]), (1.35, 0.25))
        self.assertEqual(back["total_cost_usd"], 51.35)  # 50 + 1.10 + 0.25
        self.assertEqual(back["result_usd"], 8.65)

    def test_a_derive_quote_carries_the_order_managers_settings(self):
        buy, _ = self.quote({"platformFeeRate": 0}, "--side", "buy", "--product", "call", "--underlying", "ETH",
                            "--size", "1", "--strike", "1900")
        self.assertEqual(buy["worked"], {
            "params": {"INSTRUMENT": ETH_CALL, "ACTION": "buy", "SIZE": 1.0, "WORST_PRICE": 50.0,
                       "FEE_USD": 1.1, "SIZE_STEP": 0.01, "MIN_SIZE": 0.01, "TICK_SIZE": 0.1,
                       "MAKER_FEE_RATE": 0.0001},
            "fund_usdc": 53, "at_mark_saves_usd": 1.0})
        back, _ = self.quote({"platformFeeRate": 0}, *CLOSE[1:])
        self.assertEqual((back["worked"]["params"]["ACTION"], back["worked"]["params"]["WORST_PRICE"],
                          back["worked"]["fund_usdc"], back["worked"]["at_mark_saves_usd"]),
                         ("close", 48.0, 0, 1.0))

    def test_the_parts_add_up_to_the_fee(self):
        h = helper(account()[0])
        h.PLATFORM["rate"] = 0.005
        for premium, venue in ((18.22, 0.704), (5.0, 0.6234), (77.6, 0.561685)):
            parts = h.fee_fields(venue, h.platform_fee(premium))
            self.assertAlmostEqual(parts["venue_fee_usd"] + parts["platform_fee_usd"], parts["fee_usd"], places=9)

    def test_a_budget_buys_less_once_the_platform_fee_is_counted(self):
        args = ("--side", "buy", "--product", "call", "--underlying", "ETH", "--budget", "53.66", "--strike", "1900")
        free, _ = self.quote({"platformFeeRate": 0}, *args)
        paid, _ = self.quote({"platformFeeRate": 0.005}, *args)
        self.assertEqual(free["platform_fee_usd"], 0)
        self.assertEqual((free["size"], paid["size"]), (1, 0.99))
        self.assertEqual(paid["total_cost_usd"], round(paid["premium_usd"] + paid["fee_usd"], 2))
        self.assertLessEqual(paid["max_cost_usd"], 53.66)

    def test_paradex_and_reads_that_price_nothing_never_ask(self):
        for argv in (("quote", "--venue", "paradex", "--side", "close", "--instrument", "X", "--size", "1"),
                     ("chain", "--underlying", "ETH"),
                     ("minimum", "--underlying", "ETH")):
            acp, calls = account({"platformFeeRate": 0.005})
            h = helper(acp)
            h.run_quote = lambda p, a: {}
            h.chain_rows = h.build_minimum = lambda *a, **k: {}
            run(h, *argv)
            self.assertEqual(calls, [], argv)
            self.assertEqual(h.PLATFORM["rate"], 0.0)

    def test_there_is_no_flag(self):
        code, _, err = run(helper(account({"platformFeeRate": 0})[0]), *CLOSE, "--platform-fee-rate", "0")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", err)


if __name__ == "__main__":
    unittest.main()

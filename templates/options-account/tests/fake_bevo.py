"""A scripted stand-in for the `bevo` SDK, for running duty.py offline.

`run(...)` installs a fresh fake as `bevo`, pins the clock to each check's time
(the first is the check at start, the rest are ticks), makes the jitter sleep
free, executes duty.py to the end of its ticks, and returns the fake for
assertions.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

START = 1792915200  # 2026-10-25T00:00:00Z
WALLET = "0x00000000000000000000000000000000000000a1"


class BevoError(Exception):
    pass


class FakeBevo:
    BevoError = BevoError

    def __init__(self, times, reads, state, platforms=None, refuse=()):
        self.times = list(times)
        self.reads = {path: list(value) if isinstance(value, list) else value
                      for path, value in reads.items()}
        self.state = dict(state)
        self.now = self.times[0]
        self.platforms = [] if platforms is None else platforms
        self.refuse = set(refuse)
        self.logs, self.notes, self.pushes, self.fails = [], [], [], []
        self.statuses, self.rows, self.read_calls, self.removed = [], [], [], []

    def log(self, message):
        self.logs.append(str(message))

    def notify(self, text, quiet=False, push=None):
        self.notes.append(str(text))
        self.pushes.append(push)
        return {"ok": True}

    def fail(self, reason):
        self.fails.append(str(reason))

    def status(self, next, last=None, next_at=None, **values):
        self.statuses.append((next, values))

    def platform_balance(self, site, name, usd, account="", icon=None, positions=None):
        self.rows.append({"site": site, "name": name, "usd": usd, "account": account,
                          "positions": positions})
        # The SDK answers {} for a write the server refused (logged, never raised).
        return {} if account in self.refuse else {"id": "row-1"}

    def platform_balances(self):
        if isinstance(self.platforms, BaseException):
            raise self.platforms
        return list(self.platforms)

    def spawned(self, argv, **_kwargs):
        """`subprocess.run`: records `bevo-platforms remove <id>` instead of running it."""
        if list(argv[:2]) == ["bevo-platforms", "remove"]:
            self.removed.append(argv[2])
        return subprocess.CompletedProcess(argv, 0, "", "")

    def read(self, path, params=None):
        """A list fixture answers one item per call and repeats its last."""
        self.read_calls.append((path, dict(params or {})))
        value = self.reads.get(path)
        if isinstance(value, list):
            value = value.pop(0) if len(value) > 1 else value[0]
        if callable(value):
            value = value(params or {})
        if isinstance(value, BaseException):
            raise value
        if value is None:
            raise BevoError("no fixture for %s" % path)
        return value

    def ticks(self):
        for at in self.times[1:]:
            self.now = at
            yield {"kind": "timer"}


def run(times, reads=None, state=None, params=None, platforms=None, refuse=()):
    fake = FakeBevo(times, reads or {}, state or {}, platforms, refuse)
    sys.modules["bevo"] = fake
    spec = importlib.util.spec_from_file_location("duty_under_test", ROOT / "duty.py")
    module = importlib.util.module_from_spec(spec)
    env = {"PARAMS": json.dumps(params or {})}
    with mock.patch("time.time", lambda: fake.now), mock.patch("time.sleep", lambda _s: None), \
            mock.patch("subprocess.run", fake.spawned), mock.patch.dict(os.environ, env):
        spec.loader.exec_module(module)
    return fake


def every(minutes, count, start=START):
    return [start + i * minutes * 60 for i in range(count)]


DERIVE = "https://www.derive.xyz"
PARADEX = "https://www.paradex.trade"


def venue(vid, name, site, usdc="0", worth=None, positions=(), exists=True, late=False):
    """One entry of `venues` in bevo-server's bare `/options/account` answer."""
    return {"venue": vid, "name": name, "site": site, "depositsLandLater": late, "available": True,
            "wallet": WALLET, "signerReady": True,
            "account": {"exists": exists, "usdc": usdc, "positions": list(positions),
                        "worthUsd": worth},
            "lines": []}


def derive(usdc="0", worth=None, positions=(), exists=True, subs=None):
    entry = venue("derive", "Derive", DERIVE, usdc, worth, positions, exists, late=True)
    if subs is not None:
        entry["account"]["accounts"] = list(subs)
    return entry


def subaccount(universe, sub_id, usdc, worth, positions=()):
    """One entry of Derive's `account.accounts`: a risk universe's own subaccount."""
    return {"exists": True, "subaccountId": sub_id, "universe": universe, "usdc": usdc,
            "worthUsd": worth, "positions": list(positions)}


def platform(row_id, site, account):
    """A row as `bevo.platform_balances()` lists it."""
    host = site.split("://", 1)[1].split("/", 1)[0].lower()
    return {"id": row_id, "siteHost": host[4:] if host.startswith("www.") else host,
            "account": account}


def paradex(usdc="0", worth=None, positions=(), exists=True):
    return venue("paradex", "Paradex", PARADEX, usdc, worth, positions, exists)


def accounts(*venues):
    """The bare read: Derive's legacy body at the top, every venue in `venues`."""
    return {"wallet": WALLET, "signerReady": True, "account": None, "venues": list(venues)}


def position(instrument, size, value, pnl=None):
    parts = instrument.split("-")
    strike = parts[-2]
    return {"instrument": instrument, "size": size, "underlying": parts[0],
            "strike": float(strike.replace("_", ".")), "type": parts[-1],
            "valueUsd": value, "pnlUsd": pnl, "expiresIn": "in 2 days"}

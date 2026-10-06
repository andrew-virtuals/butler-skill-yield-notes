#!/usr/bin/env python3
"""Spikes A1 and A4: can a Butler wallet actually drive a Derive account?

A1 is the only unknown that can change the architecture. Privy wallets with
sponsored gas may be smart accounts, whose EIP-712 signatures are ERC-1271
rather than a plain ECDSA recovery. Derive may or may not accept those. If it
does not, the fallback is a per-user signer EOA held by the rail, which is a
custodial model and a different legal question.

This answers it in minutes instead of a week.

    A1  register a session key scoped to options only, and read it back
    A2  reach the public API                      (already passing)
    A3  Python 3.11+ and derive-py importable
    A4  deposit a small amount of USDC from Base  (opt-in, --deposit)

Nothing here sells anything. A1 registers a key scoped to
`trade:rfq:option` + `trade:orderbook:option`, which cannot withdraw,
transfer or administer. A4 moves your own money into your own subaccount and
is skipped unless you ask for it.

SAFETY
    Use a throwaway wallet with pocket change. Never a wallet holding real
    funds, and never a wallet whose key has been in a chat window.

    The private key is read from the environment and is never printed,
    logged, or written to disk by this script.

SETUP
    python3.11 -m venv .venv && . .venv/bin/activate
    pip install derive-py
    export DERIVE_SPIKE_PRIVATE_KEY=0x...      # throwaway wallet
    export DERIVE_SPIKE_WALLET=0x...           # optional: smart-account address
                                               # if it differs from the signer

RUN
    python spikes/a1_a4_spike.py               # A1 + A3, no money moved
    python spikes/a1_a4_spike.py --deposit 20  # also A4, moves $20 USDC
"""

import argparse
import os
import sys
import time
import traceback

RESULTS = []


def record(spike, ok, detail):
    RESULTS.append((spike, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print("\n[%s] %s\n      %s" % (mark, spike, detail))


def redact(exc):
    """Never let key material reach the terminal through a traceback."""
    text = "%s: %s" % (type(exc).__name__, exc)
    key = os.environ.get("DERIVE_SPIKE_PRIVATE_KEY", "")
    if key and len(key) > 6:
        text = text.replace(key, "<redacted>")
        text = text.replace(key[2:], "<redacted>")
    return text[:400]


def spike_a3():
    """Python 3.11+, and the official SDK importable."""
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        record("A3 python", False,
               "Python %d.%d - derive-py needs >= 3.11. The container must ship "
               "3.11+, not the system 3.9." % (major, minor))
        return False
    try:
        import derive_py  # noqa: F401
        from derive_py.data_types import ProtocolScope  # noqa: F401
    except Exception as exc:
        record("A3 derive-py", False,
               "Python %d.%d is fine, but the SDK did not import: %s\n"
               "      pip install derive-py" % (major, minor, redact(exc)))
        return False
    record("A3 python + derive-py", True,
           "Python %d.%d, derive_py imports, ProtocolScope available."
           % (major, minor))
    return True


def spike_a1():
    """THE question: will Derive accept this wallet's signature?"""
    from derive_py import HTTPClient
    from derive_py.data_types import OffchainScope, ProtocolScope

    key = os.environ.get("DERIVE_SPIKE_PRIVATE_KEY")
    if not key:
        record("A1", False, "DERIVE_SPIKE_PRIVATE_KEY is not set. See SETUP above.")
        return False

    label = "butler-a1-spike"
    # Options only. No withdraw, no transfer, no admin - this is exactly the
    # scope a production Butler session key should hold.
    scopes = [ProtocolScope.TRADE_ORDERBOOK_OPTION, ProtocolScope.TRADE_RFQ_OPTION]

    try:
        client = HTTPClient.from_env()
    except Exception:
        try:
            kwargs = {"private_key": key}
            wallet = os.environ.get("DERIVE_SPIKE_WALLET")
            if wallet:
                kwargs["wallet"] = wallet
            client = HTTPClient(**kwargs)
        except Exception as exc:
            record("A1 client", False,
                   "Could not construct a client: %s\n"
                   "      If this wallet is a smart account, set DERIVE_SPIKE_WALLET "
                   "to the account address and keep the signer key separate."
                   % redact(exc))
            return False

    # Does the wallet even resolve to a Derive account?
    try:
        subaccounts = client.account.subaccounts()
        record("A1a account", True, "Derive knows this wallet: %s" % subaccounts)
    except Exception as exc:
        record("A1a account", False,
               "Derive does not recognise this wallet yet: %s\n"
               "      Onboard it once at app.derive.xyz, then re-run."
               % redact(exc))
        return False

    # The actual signature test.
    try:
        session_key = os.environ.get("DERIVE_SPIKE_SESSION_KEY")
        if not session_key:
            from eth_account import Account
            session_key = Account.create().key.hex()
            print("      (generated an ephemeral session keypair for this test)")
        from eth_account import Account as A
        pub = A.from_key(session_key).address

        client.account.set_session_key(
            public_session_key=pub,
            expiry_sec=int(time.time()) + 900,
            label=label,
            protocol_scopes=scopes,
            offchain_scopes=[OffchainScope.ACCOUNT_INFO],
        )
    except Exception as exc:
        record("A1 set_session_key", False,
               "Derive REJECTED the signature: %s\n"
               "      If this mentions ERC-1271, signature recovery or an invalid "
               "signer, A1 has failed and the custodial fallback in the plan is "
               "now the live option. Take this to review before building further."
               % redact(exc))
        return False

    # Read it back - registration is only real if Derive lists it.
    try:
        keys = client.account.session_keys().public_session_keys
        mine = [k for k in keys if getattr(k, "label", "") == label]
        if not mine:
            record("A1 readback", False,
                   "set_session_key returned without error, but no key with label "
                   "%r is listed. Treat as a FAIL." % label)
            return False
        k = mine[0]
        record("A1 set_session_key", True,
               "Derive ACCEPTED a Butler-wallet signature.\n"
               "      registered: %s\n"
               "      scopes:     %s\n"
               "      expires:    %s  (short-lived; it lapses on its own)"
               % (getattr(k, "public_session_key", "?"),
                  getattr(k, "protocol_scopes", "?"),
                  getattr(k, "expiry_sec", "?")))
        return True
    except Exception as exc:
        record("A1 readback", False, redact(exc))
        return False


def spike_a4(amount):
    """Move a small amount of the caller's own USDC into their subaccount."""
    from derive_py import HTTPClient
    try:
        client = HTTPClient.from_env()
        before = client.account.subaccounts()
        print("      subaccounts before: %s" % before)
        client.account.deposit(amount=amount, asset="USDC")
        time.sleep(10)
        after = client.account.subaccounts()
        record("A4 deposit", True,
               "Deposited %s USDC from Base. Subaccounts now: %s\n"
               "      Confirm the balance landed at app.derive.xyz." % (amount, after))
        return True
    except Exception as exc:
        record("A4 deposit", False,
               "%s\n      Check: USDC on Base, gas, and that the bridge "
               "contract is approved." % redact(exc))
        return False


def main():
    p = argparse.ArgumentParser(description="Butler x Derive spikes A1/A3/A4")
    p.add_argument("--deposit", type=float, default=None,
                   help="also run A4, depositing this many USDC from Base")
    a = p.parse_args()

    print(__doc__.split("SAFETY")[0].strip())
    print("\n" + "=" * 68)

    if not spike_a3():
        print("\nA3 failed - nothing else can run. Fix the environment first.")
        sys.exit(1)

    a1 = spike_a1()

    if a.deposit is not None:
        if not a1:
            print("\nSkipping A4: without a working signature there is nothing to test.")
        else:
            spike_a4(a.deposit)

    print("\n" + "=" * 68)
    print("SUMMARY")
    for spike, ok, _ in RESULTS:
        print("  %-28s %s" % (spike, "PASS" if ok else "FAIL"))
    failed = [s for s, ok, _ in RESULTS if not ok]
    if any(s.startswith("A1") for s in failed):
        print("\n  A1 FAILED. This is the architecture fork in the plan (section 7A):\n"
              "  fall back to a rail-controlled signer EOA, which is custodial and\n"
              "  needs legal review. Do not start the options rail until that is settled.")
    elif not failed:
        print("\n  A1 passed: Butler wallets can drive a Derive account with an\n"
              "  options-only session key. The non-custodial model in the plan holds.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print("\nunexpected: %s" % redact(exc))
        traceback.print_exc(limit=1)
        sys.exit(1)

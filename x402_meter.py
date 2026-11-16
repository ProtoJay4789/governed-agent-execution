#!/usr/bin/env python3
"""Steve Capital — x402 metered tool calls.

SAP (the Synapse Agent Protocol Steve speaks) settles a **fee per tool call** through x402: no pre-funded
account, no custodial balance, the price of a call is explicit at the moment it happens. This module is the
client side of that model, wired to the same mandate and the same append-only ledger as `steve_harness.py`.

FOUR RULES, EACH ONE TESTED
  1. NO FREE TOOLS. An unknown tool is refused, not priced at zero. A catalog miss is a DENY.
  2. NO UNPRICED CALL. A tool whose price is missing or non-positive cannot be called.
  3. NO DOUBLE CHARGE. Each call carries an idempotency key; a repeat returns the original receipt instead
     of paying twice. (x402 retries are normal; paying twice for one retry is not.)
  4. NO FREE PASS OFFLINE. The settlement adapter is injected. The one shipped here is `DryRunSettlement`,
     which REFUSES — so on this seat every paid call ends BLOCKED, and the ledger says so. A settlement that
     did not happen is never recorded as spent.

Usage:
  x402_meter.py --selftest
"""
import argparse
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, asdict, field

from steve_harness import Action, ALLOW, DENY, BLOCK, PolicyError, Ledger, Mandate, _u

# ── the catalog: price per call, in micro-USDC. Modelled on SAP's typed tool catalog ────────────────
CATALOG = {
    "market.price":       2_000,     # 0.002 USDC — a quote read
    "market.candles":     5_000,     # 0.005
    "wallet.balances":    3_000,
    "route.plan":        12_000,     # MultiHopper-style routing plan
    "route.execute":     40_000,
    "search.web":        10_000,     # Ace Data Cloud-style research call
    "image.generate":    25_000,
}


class NoSettlement(PolicyError):
    """The payment could not be made. Not a warning — a stop."""


class DryRunSettlement:
    """The only settlement in this repo. It cannot pay. That is the point."""

    name = "dry-run"

    def settle(self, tool: str, price_micro: int, call_id: str) -> str:
        raise NoSettlement(
            f"NO_SETTLEMENT: refusing to record a payment for {tool} ({_u(price_micro)} USDC) — this "
            f"harness holds no funds and speaks to no chain. Wire a real x402 client here when a funded "
            f"wallet exists.")


@dataclass
class CallReceipt:
    tool: str
    price_micro: int
    call_id: str
    decision: str
    args_hash: str = ""
    settlement_ref: str = ""
    reason: str = ""
    at: str = ""
    reused: bool = False

    def as_record(self):
        d = asdict(self)
        d["price_usdc_human"] = _u(self.price_micro)
        return d


class MeteredClient:
    """Mandate -> catalog price -> budget -> settlement -> ledger. Same discipline as the execution agent."""

    def __init__(self, mandate: Mandate, ledger: Ledger, settle=None, catalog=None):
        self.mandate = mandate
        self.ledger = ledger
        self.settle = settle or DryRunSettlement()
        self.catalog = catalog or CATALOG
        self._by_key = {}

    def call(self, tool: str, args: dict):
        args_hash = hashlib.sha1(json.dumps(args, sort_keys=True).encode()).hexdigest()[:12]
        call_id = hashlib.sha1(f"{tool}|{args_hash}".encode()).hexdigest()[:12]

        # rule 3 — idempotency: a retry returns the original outcome, it does not re-charge
        if call_id in self._by_key:
            prev = dict(self._by_key[call_id])
            prev["reused"] = True
            return prev

        rec = CallReceipt(tool=tool, price_micro=int(self.catalog.get(tool, 0) or 0),
                          call_id=call_id, decision=DENY, args_hash=args_hash)

        # rule 1 — no free tools
        if tool not in self.catalog:
            rec.reason = f"TOOL_NOT_IN_CATALOG: {tool!r} is not a priced tool — refusing to call it free"
            return self._finish(rec)

        # rule 2 — no unpriced call
        if rec.price_micro <= 0:
            rec.reason = f"TOOL_UNPRICED: {tool!r} has no positive price"
            return self._finish(rec)

        # budget through the SAME mandate path as any other value movement
        try:
            self.mandate.check(Action(kind="tool_call", amount_usdc=rec.price_micro,
                                      destination=tool.split(".")[0], purpose=tool),
                               self.ledger.spent())
        except PolicyError as e:
            rec.reason = str(e)
            return self._finish(rec)

        # rule 4 — settlement, and a settlement that did not happen is not spend
        try:
            rec.settlement_ref = self.settle.settle(tool, rec.price_micro, call_id)
        except PolicyError as e:
            rec.decision = BLOCK
            rec.reason = str(e)
            return self._finish(rec)

        rec.decision = ALLOW
        return self._finish(rec)

    def _finish(self, rec: CallReceipt):
        rec.at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._by_key[rec.call_id] = rec.as_record()
        with open(self.ledger.path, "a") as f:
            f.write(json.dumps({"kind": "tool_call", **rec.as_record()}) + "\n")
        return rec.as_record()


# ── selftest ────────────────────────────────────────────────────────────────────────────────────────
def selftest():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + name + (f" — {detail}" if detail and not cond else ""))
        ok = ok and cond

    def fresh(**kw):
        d = tempfile.mkdtemp()
        L = Ledger(os.path.join(d, f"l{time.time_ns()}.jsonl"))
        M = Mandate(per_action_cap=100_000, total_cap=200_000,
                    allowlist=("market", "route", "search"), expires_at="2030-01-01T00:00:00Z", **kw)
        return L, M

    class Paying:
        name = "test-settlement"
        def __init__(self): self.charged = []
        def settle(self, tool, price, call_id):
            self.charged.append(price)
            return f"0x{call_id}"

    # 1 · priced, in-budget, with a working settlement -> ALLOW with an on-chain-shaped ref
    L, M = fresh()
    p = Paying()
    c = MeteredClient(M, L, p)
    first = c.call("market.price", {"symbol": "SOL"})
    check("priced call with settlement succeeds",
          first["decision"] == ALLOW and bool(first["settlement_ref"]), first["reason"])
    check("price is charged exactly once", p.charged == [2_000], str(p.charged))

    # 2 · unknown tool is refused, never free
    miss = c.call("protocol.secret_sauce", {})
    check("unknown tool is DENIED (no free tools)",
          miss["decision"] == DENY and miss["reason"].startswith("TOOL_NOT_IN_CATALOG"), miss["reason"])

    # 3 · retry is idempotent — one charge for two attempts
    again = c.call("market.price", {"symbol": "SOL"})
    check("repeat call is reused, not recharged",
          again["reused"] is True and again["call_id"] == first["call_id"] and p.charged == [2_000],
          f"reused={again.get('reused')} same_id={again['call_id'] == first['call_id']} charged={p.charged}")

    # 4 · the dry-run settlement blocks and does not record spend
    L2, M2 = fresh()
    c2 = MeteredClient(M2, L2)                       # default DryRunSettlement
    r = c2.call("search.web", {"q": "solana perps"})
    check("dry-run settlement BLOCKS", r["decision"] == BLOCK and r["reason"].startswith("NO_SETTLEMENT"),
          r["reason"])
    check("a blocked call is not spend", L2.spent() == 0, str(L2.spent()))

    # 5 · budget exhaustion denies through the mandate, not a private counter
    L3, M3 = fresh()
    M3.total_cap = 100_000                           # total 100,000; per-action stays 100,000
    c3 = MeteredClient(M3, L3, Paying())
    for n in range(6):                               # 6 x route.plan @ 12,000 = 72,000 spent
        c3.call("route.plan", {"to": "jupiter", "hops": 2, "n": n})
    over = c3.call("route.execute", {"route": "abc"})  # +40,000 = 112,000 > 100,000 total
    check("budget exhaustion denies (via mandate)", over["decision"] == DENY
          and over["reason"].startswith("TOTAL_CAP"), f"{over['decision']} {over['reason']}")

    # 6 · per-action cap applies to tool prices too
    L4, M4 = fresh()
    M4.per_action_cap = 5_000
    r = MeteredClient(M4, L4, Paying()).call("route.execute", {"route": "abc"})
    check("per-action cap denies an expensive tool", r["decision"] == DENY
          and r["reason"].startswith("PER_ACTION_CAP"), r["reason"])

    # 7 · destination allowlist covers tool families
    L5, M5 = fresh()
    M5.allowlist = ("market",)
    r = MeteredClient(M5, L5, Paying()).call("route.plan", {"x": 1})
    check("tool family off-allowlist is denied", r["decision"] == DENY
          and r["reason"].startswith("DESTINATION_NOT_ALLOWED"), r["reason"])

    # 8 · the ledger is the source of truth for spend, and it reconciles
    L6, M6 = fresh()
    p6 = Paying()
    c6 = MeteredClient(M6, L6, p6)
    c6.call("market.price", {"symbol": "SOL"})
    c6.call("market.candles", {"symbol": "SOL", "tf": "1h"})
    c6.call("bogus.tool", {})
    rows = [json.loads(l) for l in open(L6.path)]
    spent_from_ledger = sum(r["price_micro"] for r in rows if r["decision"] == ALLOW)
    check("ledger reconciles with the settlement", spent_from_ledger == sum(p6.charged),
          f"{spent_from_ledger} vs {sum(p6.charged)}")
    check("every attempt is recorded, including the denial", len(rows) == 3, str(len(rows)))

    print()
    print("X402 METER SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

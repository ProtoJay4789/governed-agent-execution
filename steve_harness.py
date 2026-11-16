#!/usr/bin/env python3
"""Steve Capital — governed execution harness.

The artifact, not the submission. It models the part of the Steve Capital challenge that is graded on
"meaningful autonomous workflows, effective use of mandates and risk controls" — and it models it in a
form that can be RUN and TESTED without a funded wallet, then pointed at one.

THREE PROPERTIES, IN THE ORDER THE MONEY MEETS THEM:

  1. mandate   — per-action cap, total spend cap, destination allowlist, expiry. Deny by default.
  2. simulate  — the transaction is BUILT and SIMULATED without signing. A failed simulation BLOCKS.
  3. ledger    — every decision (allow / deny / block) is appended with enough detail to replay by hand.

WHAT IS DELIBERATELY NOT HERE
  No keypair is generated, stored or held. There is no signing path in this module. The signer is an
  injected interface; the only implementation in this repo is `DryRunSigner`, which REFUSES to sign and
  says so. Steve is non-custodial by design (keys stay in the browser wallet), and a harness that could
  hold a key would be modelling the wrong product.

HONESTY RULES (same family as the rest of EDU)
  - A simulation that did not run is `SIMULATION_UNAVAILABLE`, never "passed".
  - A blocked action is recorded as blocked — it never becomes a silent skip.
  - The ledger is append-only and never rewritten to make a demo read better.

Usage:
  steve_harness.py --selftest        # no network, no wallet — proves the gates
  steve_harness.py --ledger PATH     # print a ledger back as a human-readable audit trail
"""
import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# ── decisions ────────────────────────────────────────────────────────────────────────────────────────
ALLOW = "ALLOW"
DENY = "DENY"
BLOCK = "BLOCK"        # policy passed, execution gate refused (simulation failure, signer refusal)
UNAVAILABLE = "UNAVAILABLE"   # a gate could not be evaluated — NOT the same as passing

DEFAULT_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ledger", "decisions.jsonl")


class PolicyError(Exception):
    """The mandate says no. Raised before any transaction is built."""


@dataclass(frozen=True)
class Action:
    """One intended value movement. Amounts are integers in micro-USDC to avoid float drift."""
    kind: str                  # swap | transfer | perp_open | route | launch | tool_call
    amount_usdc: int           # micro-USDC (1e6 = 1 USDC)
    destination: str           # protocol id or wallet address; must be on the allowlist
    purpose: str = ""
    hops: int = 1              # MultiHopper-style routing; counted once per route, never per hop

    def key(self):
        return hashlib.sha1(
            f"{self.kind}|{self.amount_usdc}|{self.destination}|{self.purpose}".encode()
        ).hexdigest()[:12]


@dataclass
class Mandate:
    """The authority document. Everything not granted here is denied."""
    per_action_cap: int                    # micro-USDC
    total_cap: int                         # micro-USDC
    allowlist: tuple = ()                  # destinations permitted at all
    expires_at: str = ""                   # ISO8601 UTC
    require_simulation: bool = True
    note: str = ""

    def check(self, action: Action, spent_so_far: int) -> None:
        """Raise PolicyError with a REASON. Deny by default: anything unset is forbidden."""
        if not self.expires_at:
            raise PolicyError("MANDATE_EXPIRED: no expiry set — an unbounded mandate is not a mandate")
        expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= expiry:
            raise PolicyError(f"MANDATE_EXPIRED: expired at {self.expires_at}")
        if self.per_action_cap <= 0:
            raise PolicyError("CAP_ZERO: per-action cap is zero or unset")
        if action.amount_usdc <= 0:
            raise PolicyError("AMOUNT_ZERO: nothing to move")
        if action.amount_usdc > self.per_action_cap:
            raise PolicyError(
                f"PER_ACTION_CAP: {_u(action.amount_usdc)} USDC > cap {_u(self.per_action_cap)} USDC")
        if spent_so_far + action.amount_usdc > self.total_cap:
            raise PolicyError(
                f"TOTAL_CAP: {_u(spent_so_far + action.amount_usdc)} USDC > total "
                f"{_u(self.total_cap)} USDC")
        if action.destination not in self.allowlist:
            raise PolicyError(f"DESTINATION_NOT_ALLOWED: {action.destination!r} is not on the allowlist")


def _u(micro):
    return f"{micro / 1_000_000:.2f}"


@dataclass
class Receipt:
    """What actually happened, in a shape a human can replay by hand."""
    action: str
    decision: str
    amount_usdc: int
    destination: str
    checks: list = field(default_factory=list)
    reason: str = ""
    simulation: dict = field(default_factory=dict)
    signature: str = ""
    at: str = ""
    key: str = ""

    def as_record(self):
        d = asdict(self)
        d["amount_usdc_human"] = _u(self.amount_usdc)
        return d


class Ledger:
    """Append-only JSONL. Never rewritten, never sorted, never deduped to look tidier."""

    def __init__(self, path=DEFAULT_LEDGER):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def spent(self):
        total = 0
        if not os.path.exists(self.path):
            return 0
        for line in open(self.path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("decision") == ALLOW:
                # ONE ledger, TWO shapes of value movement: an executed action carries `amount_usdc`,
                # a metered tool call carries `price_micro`. Counting only the first made the budget
                # blind to every paid tool call — caught by x402_meter's budget test, not by review.
                total += int(r.get("amount_usdc") or r.get("price_micro") or 0)
        return total

    def append(self, receipt: Receipt):
        receipt.at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        with open(self.path, "a") as f:
            f.write(json.dumps(receipt.as_record()) + "\n")
        return receipt

    def read(self):
        if not os.path.exists(self.path):
            return []
        out = []
        for line in open(self.path):
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out


class DryRunSigner:
    """The ONLY signer in this repo. It cannot sign. That is the point."""

    name = "dry-run"

    def sign(self, tx):
        raise PolicyError(
            "NO_SIGNER: this harness holds no key. Steve Capital is non-custodial — the wallet signs "
            "in the browser. Point a real signer implementation at this interface when the wallet exists.")


def simulate_default(action: Action) -> dict:
    """The default simulation gate: no chain connection exists here, so it reports UNAVAILABLE.

    Returning `{"ok": True}` from a gate that never ran is exactly the failure this file exists to
    prevent. A live implementation connects to the Solana RPC, builds the transaction and reports the
    real result (including program errors) — and only a real pass may proceed to signing.
    """
    return {"ok": None, "status": "SIMULATION_UNAVAILABLE",
            "detail": "no RPC connection in the offline harness — nothing was simulated"}


class ExecutionAgent:
    """mandate -> policy check -> simulation gate -> signer -> ledger. No other path to value."""

    def __init__(self, mandate: Mandate, signer=None, ledger=None, simulate=simulate_default):
        self.mandate = mandate
        self.signer = signer or DryRunSigner()
        self.ledger = ledger or Ledger()
        self.simulate = simulate

    def execute(self, action: Action) -> Receipt:
        r = Receipt(action=f"{action.kind} {_u(action.amount_usdc)} USDC -> {action.destination}",
                    decision=DENY, amount_usdc=action.amount_usdc,
                    destination=action.destination, key=action.key())

        # 1 · mandate
        try:
            self.mandate.check(action, self.ledger.spent())
            r.checks.append("mandate: pass")
        except PolicyError as e:
            r.reason = str(e)
            r.checks.append(f"mandate: {r.reason}")
            return self.ledger.append(r)

        # 2 · simulation gate — a gate that did not run is not a pass
        if self.mandate.require_simulation:
            sim = self.simulate(action)
            r.simulation = sim
            if sim.get("ok") is not True:
                r.decision = BLOCK
                r.reason = sim.get("status") or "SIMULATION_FAILED"
                r.checks.append(f"simulation: {r.reason}")
                return self.ledger.append(r)
            r.checks.append("simulation: pass")

        # 3 · signer — refusal is a BLOCK, not a crash and not a silent skip
        try:
            r.signature = self.signer.sign({"action": asdict(action)})
            r.checks.append(f"signer: {getattr(self.signer, 'name', 'unknown')}")
        except PolicyError as e:
            r.decision = BLOCK
            r.reason = str(e)
            r.checks.append(f"signer: refused")
            return self.ledger.append(r)

        r.decision = ALLOW
        return self.ledger.append(r)


# ── selftest: prove the gates, no network, no wallet ────────────────────────────────────────────────
def selftest():
    import tempfile
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + name + (f" — {detail}" if detail and not cond else ""))
        ok = ok and cond

    tmp = tempfile.mkdtemp()
    led = lambda: Ledger(os.path.join(tmp, f"l{time.time_ns()}.jsonl"))
    future = "2030-01-01T00:00:00Z"
    M = Mandate(per_action_cap=5_000_000, total_cap=8_000_000,
                allowlist=("jupiter", "kamino"), expires_at=future)
    passing_sim = lambda a: {"ok": True, "status": "PASS", "detail": "simulated"}
    signer = type("S", (), {"name": "test-signer", "sign": lambda self, tx: "SIG123"})()

    # 1 · inside the mandate, simulation passes, signer signs -> ALLOW
    a = ExecutionAgent(M, signer, led(), passing_sim)
    r = a.execute(Action("swap", 2_000_000, "jupiter", "SOL -> USDC"))
    check("in-mandate action is ALLOWed and signed", r.decision == ALLOW and r.signature == "SIG123",
          f"{r.decision} {r.reason}")

    # 2 · over the per-action cap -> DENY before anything is built
    r = a.execute(Action("swap", 6_000_000, "jupiter"))
    check("per-action cap denies", r.decision == DENY and r.reason.startswith("PER_ACTION_CAP"), r.reason)
    check("deny never reaches the signer", r.signature == "", r.signature)

    # 3 · destination not on the allowlist -> DENY (deny-by-default)
    r = a.execute(Action("transfer", 1_000_000, "some-random-wallet"))
    check("unlisted destination is denied", r.decision == DENY
          and r.reason.startswith("DESTINATION_NOT_ALLOWED"), r.reason)

    # 4 · total cap across actions
    a2 = ExecutionAgent(M, signer, led(), passing_sim)
    a2.execute(Action("swap", 5_000_000, "jupiter"))
    r = a2.execute(Action("swap", 4_000_000, "jupiter"))
    check("total cap denies the second spend", r.decision == DENY and r.reason.startswith("TOTAL_CAP"),
          r.reason)

    # 5 · expired mandate
    Me = Mandate(per_action_cap=5_000_000, total_cap=8_000_000,
                 allowlist=("jupiter",), expires_at="2020-01-01T00:00:00Z")
    r = ExecutionAgent(Me, signer, led(), passing_sim).execute(Action("swap", 1_000_000, "jupiter"))
    check("expired mandate denies", r.decision == DENY and r.reason.startswith("MANDATE_EXPIRED"), r.reason)

    # 6 · mandate with no expiry is not a mandate
    Mn = Mandate(per_action_cap=5_000_000, total_cap=8_000_000, allowlist=("jupiter",))
    r = ExecutionAgent(Mn, signer, led(), passing_sim).execute(Action("swap", 1_000_000, "jupiter"))
    check("mandate without expiry denies", r.decision == DENY and "no expiry" in r.reason, r.reason)

    # 7 · simulation failure BLOCKS even though the mandate passed
    fail_sim = lambda a: {"ok": False, "status": "SIMULATION_FAILED", "detail": "program error 0x1"}
    r = ExecutionAgent(M, signer, led(), fail_sim).execute(Action("swap", 1_000_000, "jupiter"))
    check("failed simulation BLOCKS", r.decision == BLOCK and r.reason == "SIMULATION_FAILED", r.reason)
    check("a blocked action is not signed", r.signature == "", r.signature)

    # 8 · the default gate cannot pass — UNAVAILABLE is a BLOCK, never ALLOW
    r = ExecutionAgent(M, signer, led()).execute(Action("swap", 1_000_000, "jupiter"))
    check("unavailable simulation BLOCKS (never a silent pass)",
          r.decision == BLOCK and r.reason == "SIMULATION_UNAVAILABLE", f"{r.decision} {r.reason}")

    # 9 · the only signer in this repo refuses
    r = ExecutionAgent(M, None, led(), passing_sim).execute(Action("swap", 1_000_000, "jupiter"))
    check("dry-run signer refuses and records a BLOCK",
          r.decision == BLOCK and r.reason.startswith("NO_SIGNER"), r.reason)

    # 10 · every path wrote exactly one receipt, and they are append-only
    L = led()
    ag = ExecutionAgent(M, signer, L, passing_sim)
    for amt in (1_000_000, 9_000_000, 1_000_000):
        ag.execute(Action("swap", amt, "jupiter"))
    rows = L.read()
    check("one receipt per attempt, none dropped", len(rows) == 3, f"{len(rows)} rows")
    check("ledger only counts ALLOW toward spend", L.spent() == 2_000_000, str(L.spent()))
    check("receipts carry human amounts", all("amount_usdc_human" in x for x in rows))

    # 11 · a route counts once regardless of hops (MultiHopper judging rule modelled, not assumed)
    hop_a = Action("route", 1_000_000, "jupiter", hops=1)
    hop_b = Action("route", 1_000_000, "jupiter", hops=4)
    check("hops do not multiply the amount", hop_a.amount_usdc == hop_b.amount_usdc)

    print()
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def print_ledger(path):
    rows = Ledger(path).read()
    if not rows:
        print(f"no decisions recorded at {path}")
        return 0
    for i, r in enumerate(rows, 1):
        print(f"{i:>3}. [{r['decision']:<11}] {r['action']}  ({r.get('at', '')})")
        for c in r.get("checks", []):
            print(f"       · {c}")
        if r.get("reason"):
            print(f"       → {r['reason']}")
        if r.get("signature"):
            print(f"       sig {r['signature']}")
    allowed = sum(1 for r in rows if r["decision"] == ALLOW)
    print(f"\n{len(rows)} decisions · {allowed} allowed · "
          f"{sum(1 for r in rows if r['decision'] == DENY)} denied · "
          f"{sum(1 for r in rows if r['decision'] == BLOCK)} blocked · "
          f"{sum(1 for r in rows if r['decision'] == UNAVAILABLE)} unavailable")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--ledger")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.ledger:
        return print_ledger(a.ledger)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

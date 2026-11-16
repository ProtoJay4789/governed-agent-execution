#!/usr/bin/env python3
"""Steve Capital — one command that runs the whole offline proof and prints what it measured.

    python3 demo.py

Writes `ledger/decisions.jsonl` from scratch and prints a summary. Nothing here touches a chain, a
wallet or a paid API. Every line of output below is produced by the code in this directory.

Exit 0 = the demonstration is coherent. It does NOT mean the bounty is won, a wallet is funded, or any
on-chain fact exists. Those are separate and are labelled separately.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger", "decisions.jsonl")
sys.path.insert(0, HERE)

from steve_harness import Action, ExecutionAgent, Ledger, Mandate, ALLOW, BLOCK, DENY  # noqa: E402
from x402_meter import CATALOG, MeteredClient  # noqa: E402


class DryRun:
    """Offline everything: no signer, no settlement, no chain. Both refuse by design."""
    pass


def main():
    # fresh ledger so the demo is reproducible and never mixes with a previous run
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    if os.path.exists(LEDGER):
        os.remove(LEDGER)

    ledger = Ledger(LEDGER)
    mandate = Mandate(
        per_action_cap=5_000_000,          # 5 USDC per action
        total_cap=8_000_000,               # 8 USDC total — well under the 20 USDC the challenge requires
        allowlist=("jupiter", "kamino", "multihopper", "market", "route", "search"),
        expires_at="2030-01-01T00:00:00Z",
        note="dry-run mandate — no key, no funds",
    )

    print("STEVE CAPITAL — offline demonstration")
    print(f"mandate: {mandate.per_action_cap/1e6:.2f} USDC/action · "
          f"{mandate.total_cap/1e6:.2f} USDC total · expires {mandate.expires_at}")
    print()

    # pass 1 — execution agent, default gates (simulation unavailable, signer refuses)
    print("── execution agent (default gates) ─────────────────────────────────────────")
    agent = ExecutionAgent(mandate, ledger=ledger)
    plan = [
        Action("swap", 1_000_000, "jupiter", "SOL -> USDC, 1 USDC"),
        Action("perp_open", 2_000_000, "adrena", "gold long — destination not on the allowlist"),
        Action("route", 1_000_000, "multihopper", "agent treasury distribution, 3 hops", hops=3),
        Action("launch", 9_000_000, "meteora", "over the per-action cap"),
    ]
    for a in plan:
        r = agent.execute(a)
        print(f"  {a.kind:<10} {a.amount_usdc/1e6:>5.2f} USDC -> {a.destination:<12} "
              f"{r.decision:<6} {r.reason[:52] or '(no reason)'}")

    # pass 2 — metered tool calls, default settlement (refuses)
    print()
    print("── x402 metered tool calls (default settlement) ────────────────────────────")
    client = MeteredClient(mandate, ledger)
    for tool, args in [("market.price", {"symbol": "SOL"}),
                       ("route.plan", {"to": "jupiter", "hops": 3}),
                       ("protocol.secret_sauce", {})]:
        r = client.call(tool, args)
        price = r["price_micro"] / 1e6
        print(f"  {tool:<22} {price:>6.3f} USDC  {r['decision']:<6} {r['reason'][:46] or '(no reason)'}")

    # summary, computed from the ledger — not from the print statements above
    rows = ledger.read()
    counts = {k: sum(1 for r in rows if r["decision"] == k) for k in (ALLOW, DENY, BLOCK)}
    print()
    print("── ledger summary (read back from disk) ────────────────────────────────────")
    print(f"  receipts: {len(rows)}  ·  allowed {counts[ALLOW]}  ·  denied {counts[DENY]}  ·  blocked {counts[BLOCK]}")
    print(f"  spend recorded: {ledger.spent()/1e6:.2f} USDC")
    print()
    if counts[ALLOW]:
        print("  ⚠️  an action was ALLOWED offline — this should be impossible without a signer.")
        return 1
    print("  0 allowed is CORRECT: no signer, no settlement, no chain on this machine.")
    print("  The gates are proven; the wallet is not funded. Those are different claims.")
    print()
    print("── selftests ───────────────────────────────────────────────────────────────")
    for script in ("steve_harness.py", "x402_meter.py"):
        p = subprocess.run([sys.executable, os.path.join(HERE, script), "--selftest"],
                           capture_output=True, text=True)
        last = [l for l in p.stdout.strip().splitlines() if "SELFTEST" in l]
        print(f"  {script:<18} exit={p.returncode}  {last[0] if last else '(no result)'}")
        if p.returncode != 0:
            print(p.stdout[-800:])
            return 1
    print()
    print("ledger:", LEDGER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

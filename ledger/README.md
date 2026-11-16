# Example ledger — what a governed run actually looks like

This file is **output**, not input. It is regenerated every time you run `python3 demo.py`, and it is committed
so a reader can see the audit trail without executing anything.

Seven attempts, seven records. Read the decision column, not the prose.

```
{"kind": "execution", "action": "swap 1.00 USDC -> jupiter", "decision": "BLOCK",
 "checks": ["mandate: pass", "simulation: SIMULATION_UNAVAILABLE"], ...}
```

| # | what was attempted | decision | gate that stopped it |
|---|---|---|---|
| 1 | swap 1.00 USDC → jupiter (in mandate) | **BLOCK** | simulation never ran → `SIMULATION_UNAVAILABLE` |
| 2 | perp_open 2.00 USDC → adrena | **DENY** | destination not on the allowlist |
| 3 | route 1.00 USDC → multihopper, 3 hops | **BLOCK** | `SIMULATION_UNAVAILABLE` |
| 4 | launch 9.00 USDC → meteora | **DENY** | per-action cap 5.00 |
| 5 | tool call `market.price` 0.002 USDC | **BLOCK** | `NO_SETTLEMENT` — no funds on this machine |
| 6 | tool call `route.plan` 0.012 USDC | **BLOCK** | `NO_SETTLEMENT` |
| 7 | tool call `protocol.secret_sauce` | **DENY** | tool not in the catalog (no free tools) |

**0 allowed. 0.00 USDC spent. That is the correct result offline** — there is no key here to sign with and no
chain to settle against, so nothing may pass. A ledger showing a successful swap on a machine with no wallet
would be a fabrication.

The point of the file is the opposite of a demo reel: it is proof that the refusals fire, in order, and that
every attempt — including the ones that never happened — left exactly one record.

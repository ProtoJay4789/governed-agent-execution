# Steve Capital — governed execution harness

A runnable model of **the part of the Steve Capital challenge that is graded on agent quality**: mandates,
simulation-before-signature, and a provenance ledger. Built to be demonstrated **without a funded wallet**,
then pointed at one.

```
mandate → policy check → simulation gate → signer → append-only receipt
```

Every value movement passes all four gates in that order, or it does not happen. There is no side door.

## Run it

```sh
python3 steve_harness.py --selftest      # 15 checks, no network, no wallet — proves each gate
python3 steve_harness.py --ledger ledger/decisions.jsonl   # replay a ledger as an audit trail
```

`--selftest` output, measured 2026-11-15:

```
✅ in-mandate action is ALLOWed and signed        ✅ failed simulation BLOCKS
✅ per-action cap denies                          ✅ a blocked action is not signed
✅ deny never reaches the signer                  ✅ unavailable simulation BLOCKS (never a silent pass)
✅ unlisted destination is denied                 ✅ dry-run signer refuses and records a BLOCK
✅ total cap denies the second spend              ✅ one receipt per attempt, none dropped
✅ expired mandate denies                         ✅ ledger only counts ALLOW toward spend
✅ mandate without expiry denies                  ✅ receipts carry human amounts
                                                  ✅ hops do not multiply the amount
SELFTEST PASS
```

## What each gate means

| Gate | Behaviour | Why it is here |
|---|---|---|
| **mandate** | per-action cap, total cap, destination allowlist, expiry. Anything unset is **denied**. | A cap that defaults to "unlimited" is not a control. |
| **simulation** | build and simulate the transaction **without signing**. A failure **blocks**; a gate that never ran reports `SIMULATION_UNAVAILABLE` and also blocks. | Steve's own docs: a failed simulation blocks the action. **Not run ≠ passed.** |
| **signer** | an injected interface. The only implementation in this repo is `DryRunSigner`, which **refuses**. | Steve is non-custodial — keys stay in the browser wallet. A harness that could hold a key would be modelling the wrong product. |
| **ledger** | append-only JSONL, one receipt per attempt, human-readable amounts, replayable by hand. | The challenge judges "effective use of mandates and risk controls" — that has to be *evidence*, not a claim. |

## A worked ledger (real output, dry-run mandate)

```
1. [BLOCK] swap 1.00 USDC -> jupiter      · mandate: pass · simulation: pass · signer: refused
2. [DENY ] perp_open 2.00 USDC -> adrena  · DESTINATION_NOT_ALLOWED
3. [BLOCK] route 1.00 USDC -> multihopper · mandate: pass · simulation: pass · signer: refused
4. [DENY ] launch 9.00 USDC -> meteora    · PER_ACTION_CAP 9.00 > 5.00
4 decisions · 0 allowed · 2 denied · 2 blocked · 0 unavailable
```

**Zero allowed is the correct result offline.** Nothing can be signed here, so nothing may pass. A harness
that showed `ALLOW` rows on a machine with no wallet would be lying.

## What is NOT built here, and is labelled as such

- **No signing path.** `NO_SIGNER` is a feature. When a funded wallet exists, implement `sign()` against the
  browser wallet (or a signing service), and the rest of the pipeline is unchanged.
- **No chain connection.** `simulate_default()` returns `UNAVAILABLE` by design; a live version talks to a
  Solana RPC and reports real program errors.
- **No XP, no Arena activity, no volume.** Those are on-chain facts on OOBE's platform. The challenge's
  hard gate — **fund the agent wallet with ≥ 20 USDC** — is untouched by this repo. See `REQUIREMENTS.md`.

## Files

| File | What |
|---|---|
| `WRITEUP.md` | the public architecture piece — the submission prose and the portfolio link |
| `REQUIREMENTS.md` | the challenge's hard gates, side tracks and judging criteria, extracted from the live listing and docs |
| `steve_harness.py` | the agent: mandate, simulation gate, signer interface, ledger — **15 selftest checks** |
| `x402_meter.py` | metered tool calls: typed price catalog, idempotent retries, budget, settlement adapter — **11 selftest checks** |
| `demo.py` | one command: runs both agents against a fresh ledger and prints what it measured |
| `ledger/decisions.jsonl` | the append-only audit trail the demo produces |

## Metered tool calls (x402)

`x402_meter.py` models SAP's per-call settlement: a typed catalog with a price per call, an injected
settlement adapter, and four rules that are each tested — **no free tools** (an unknown tool is refused,
never priced at zero), **no unpriced call**, **no double charge** (idempotency key on retries), **no
imaginary payment** (the shipped adapter refuses, so nothing is recorded as spent).

```
$ python3 demo.py
  market.price            0.002 USDC  BLOCK  NO_SETTLEMENT
  route.plan              0.012 USDC  BLOCK  NO_SETTLEMENT
  protocol.secret_sauce   0.000 USDC  DENY   TOOL_NOT_IN_CATALOG
```

**A bug the tests caught:** `Ledger.spent()` originally summed only `amount_usdc` and ignored
`price_micro`, so the budget was blind to every metered call. Fixed — one ledger, both shapes of value
movement — and the budget-exhaustion test now fails loudly if that regresses.

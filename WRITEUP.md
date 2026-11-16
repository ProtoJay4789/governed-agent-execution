# Governed autonomy: what an agent should have to prove before it moves money

*Built for the Steve Capital Agent Challenge (OOBE Protocol). This is the submission's write-up and the
repo's front door. Everything claimed here is produced by code in this repository; the commands that
produce it are at the bottom.*

---

## The problem, stated without decoration

Every agent framework now advertises "autonomous execution." Almost none of them can answer the question an
institution asks first: **what stopped it?**

An agent that moves capital has three jobs, and they are not the same job:

1. decide what to do,
2. prove it is permitted to do it,
3. leave a record that survives the person who ran it.

Most systems do (1) well and treat (2) and (3) as logging. That ordering is backwards. A guardrail that
runs *after* the transaction is a postmortem, not a control.

Steve Capital's own runtime docs describe the right architecture — a command bus, policy checks, a
simulation gate that blocks rather than warns, mandates with per-wallet thresholds, and a provenance
ledger. This repository is a small, runnable model of that discipline, extracted so it can be inspected
line by line.

## The four gates

```
mandate → policy check → simulation gate → signer → append-only receipt
```

**1 · Mandate.** Per-action cap, total spend cap, destination allowlist, expiry. Everything not granted is
denied — including the case most systems get wrong: **a mandate with no expiry is refused**, because an
unbounded mandate is not a mandate.

**2 · Policy check.** Runs before a transaction is built. A destination that is not on the allowlist cannot
be paid, whatever the amount. A deny never reaches the signer — the test asserts the signature is empty.

**3 · Simulation gate.** The transaction is built and simulated **without signing and without broadcasting**.
Three outcomes, and they are deliberately distinct:

| Outcome | Effect |
|---|---|
| simulation passed | proceed to the signer |
| simulation failed | **BLOCK**, recorded with the program error |
| simulation could not run | **BLOCK** as `SIMULATION_UNAVAILABLE` |

That third row is the one that matters. A gate that never ran must never read as a pass; collapsing
"unavailable" into "fine" is how a monitor starts reporting silence as a fact.

**4 · Append-only receipt.** One JSONL line per attempt — allow, deny and block alike — with human-readable
amounts and enough detail to replay the decision by hand. The ledger is never rewritten, never deduped, and
never sorted to look tidier.

## Metered tool calls: x402 as a budget, not a bill

SAP settles a fee **per tool call** through x402: no pre-funded balance, no custodial account, the price of
a call explicit at the moment it happens. The client here applies four rules:

- **No free tools.** An unknown tool is *refused*, not priced at zero.
- **No unpriced call.** A tool with a missing or non-positive price cannot be called.
- **No double charge.** Each call carries an idempotency key; a retry returns the original receipt instead
  of paying twice — because x402 retries are normal, and paying twice for one retry is not.
- **No imaginary payment.** The settlement adapter is injected; the one shipped here **refuses**. A payment
  that did not happen is never recorded as spend.

Tool prices live in a typed catalog (`market.price` 0.002 USDC, `route.plan` 0.012, `search.web` 0.010 …),
which is the same shape SAP publishes: **tool discovery is data, not prompt folklore.**

## What the build actually measured

```
$ python3 demo.py

── execution agent (default gates) ─────────────────────────────
  swap        1.00 USDC -> jupiter      BLOCK  SIMULATION_UNAVAILABLE
  perp_open   2.00 USDC -> adrena       DENY   DESTINATION_NOT_ALLOWED
  route       1.00 USDC -> multihopper  BLOCK  SIMULATION_UNAVAILABLE
  launch      9.00 USDC -> meteora      DENY   PER_ACTION_CAP 9.00 > 5.00

── x402 metered tool calls (default settlement) ────────────────
  market.price            0.002 USDC  BLOCK  NO_SETTLEMENT
  route.plan              0.012 USDC  BLOCK  NO_SETTLEMENT
  protocol.secret_sauce   0.000 USDC  DENY   TOOL_NOT_IN_CATALOG

── ledger summary (read back from disk) ────────────────────────
  receipts: 7  ·  allowed 0  ·  denied 3  ·  blocked 4
  spend recorded: 0.00 USDC

── selftests ───────────────────────────────────────────────────
  steve_harness.py   exit=0  SELFTEST PASS        (15 checks)
  x402_meter.py      exit=0  X402 METER SELFTEST PASS   (11 checks)
```

**Zero allowed, offline, is the correct result.** No key is held here, no chain is contacted, no
settlement can occur. A harness that printed `ALLOW` rows on a machine with nothing to sign would be
theatrical. The gates are proven; the wallet is not funded; those are two different claims and this
write-up keeps them apart.

## Two bugs the tests caught that review did not

Worth stating, because "it has tests" is cheap unless the tests found something.

1. **The budget was blind to tool calls.** `Ledger.spent()` summed `amount_usdc` (executed actions) and
   ignored `price_micro` (metered calls), so a run could spend without limit through paid tools. Found by
   the budget-exhaustion test, fixed by counting both shapes in one ledger.
2. **A test compared against a rebound variable.** An earlier draft of the idempotency check passed only
   because the deny path had overwritten the receipt it was comparing to — it was asserting nothing. Both
   are now asserted explicitly, with the failing values printed in the message.

## What this is not

- **Not a live agent.** There is no signer, no RPC connection and no funded wallet. `NO_SIGNER` and
  `NO_SETTLEMENT` are features of the offline build, not gaps papered over.
- **Not a claim of challenge XP.** Arena XP, trading volume and token launches are on-chain facts on
  OOBE's platform. `REQUIREMENTS.md` lists the hard gate this repo does not satisfy: a funded agent wallet
  of at least 20 USDC, signed from a browser wallet, because Steve Capital is non-custodial by design.
- **Not a strategy.** It says nothing about *which* trades are good. It is about whether an agent is
  allowed to make them, and whether anyone can prove afterwards what it did.

## Reproducing everything above

```sh
python3 demo.py                 # the full demonstration + both selftests
python3 steve_harness.py --selftest
python3 x402_meter.py --selftest
python3 steve_harness.py --ledger ledger/decisions.jsonl   # replay the audit trail
```

Python 3.11+, standard library only. No dependencies, no network, no keys.

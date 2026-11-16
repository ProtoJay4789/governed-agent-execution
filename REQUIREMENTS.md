# Steve Capital — Challenge Requirements (extracted 2026-11-15)

**Source:** `superteam.fun/api/listings/details/build-an-autonomous-capital-agent-on-solana-and-compete-for-dollar500-in-rewards`
(20,989 bytes fetched), plus 11 pages of live docs at `steve.oobeprotocol.ai/docs`.

This file is the **brief the harness is built against**. Every requirement below is quoted or paraphrased from
the listing — not invented.

---

## 1 · Hard eligibility (the submission is void without these)

| # | Requirement | Where it bites |
|---|---|---|
| H1 | **Fund the agent wallet with ≥ 20 USDC** (or equivalent in SOL) | A **precondition**, not a step. No wallet, no submission. |
| H2 | **Deploy at least one autonomous agent on Steve Capital** | the agent exists on their runtime, not just in our repo |
| H3 | **Generate verified activity recorded through Steve Arena** | their XP ledger must have our wallet's facts |
| H4 | **Provide agent details, wallet address, relevant activity evidence** | solscan links |
| H5 | **Include links to social content for verification; tag @OOBEonSol and @SteveCapitalOS** | public posts are a judged input |
| H6 | **Submit through Superteam Earn** | the eligibility question is verbatim: *"Share your agent wallet address + any transaction link on Solana explorer / solscan if relevant."* |

## 2 · Optional side tracks (each adds its own evidence)

**MultiHopper — 125 USDC pool** (60 routing volume / 40 most successful transfers / 25 best integration)
- Execute qualifying MultiHopper transaction(s) **through the Steve agent on Solana mainnet**
- Public X post tagging **@Multihopper, @OOBEonSol, @SteveCapitalOS**, explaining the workflow, the routing
  logic and the purpose of the transfers
- Submit wallet address + transaction signatures/Explorer links + the post
- Volume counted **once per route** regardless of hops; circular/self-transfers excluded

**Ace Data Cloud — 125 USD value** (75 USDC 1st / 50 in Ace credits 2nd)
- **≥ 5 successful paid service requests using PURCHASED Ace credits** — free trial credits do not count
- A public demo or post tagging **@acedatacloud, @OOBEonSol, @SteveCapitalOS**
- Evidence of the MCP connection

## 3 · Judging criteria (main track)

1. Overall Arena activity — total verified XP
2. Trading & launch volume — spot, perpetuals, token launches
3. Product usage & ecosystem engagement — breadth and depth
4. Consistency & engagement — **sustained participation across the 30 days**
5. **Quality of execution** — meaningful autonomous workflows, effective use of mandates and risk controls
6. Social engagement & community contribution

**Anti-abuse:** wash trading, self-trading, circular transactions, artificial volume, purchased engagement are
excluded. OOBE reserves the right to disqualify.

## 4 · The platform model (from the live docs — these shape the harness)

- **Non-custodial.** Keys stay in the browser wallet; the agent only *prepares* transactions. There is **no
  agent-side key** and no deposit step. *(docs/agents/wallet)*
- **Simulation gate.** Every financial action is built and simulated **without signing or broadcasting**; a
  failed simulation **blocks** the action and records the blocked decision. *(docs/agents)*
- **Mandated thresholds.** Below a configurable threshold, actions proceed with minimal friction; above it an
  explicit signature is required. **The threshold belongs to the mandate, not to a global constant.**
- **Provenance.** Decisions persist; every tool call in history shows which tool produced a transaction.
- **SAP.** Agent registration, **x402 payment per tool call**, typed tool catalog at a well-known URL.
- **XP missions are deterministic** — XP lands when the on-chain fact exists: launch 150, feedback 75 base,
  daily engagement 40, quote Steve 25, follow Steve 25. Claims are idempotent per wallet.

## 5 · Reward split (read from `rewards`, not the headline)

`{1:125, 2:75, 3:50, 4:60, 5:40, 6:25, 7:75, 8:50}` — **$500 across 8 places**; the headline "$500" is a pool,
not a prize. Main track is 250 USDC of it; the two side tracks are 125 each.

## 6 · What our harness must therefore prove

For the write-up to be honest, the artifact must show, in code and in the ledger:

- a **mandate** with a per-action cap and a spend cap, enforced **before** anything is signed
- a **simulation gate** that blocks rather than warns, and writes the blocked decision to the ledger
- **deny-by-default routing** — a destination that is not on the allowlist cannot be paid, whatever the amount
- a **metered (x402-shaped) cost per tool call**, so the economics are explicit
- a **provenance record** per action with enough detail to replay it by hand

Anything the harness *cannot* prove offline (real XP, Arena volume, live signatures) is marked
**NEEDS LIVE WALLET** in the code and in the README. No demo data is ever presented as live results.

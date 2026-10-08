# OSA Trading Desk V1.1 — PAPER ONLY + WALLET READ ONLY

Solana research / paper-trading terminal with cinematic Polish UI. **Wallet Standard connection and browser-side public balance reads only; no signing, no on-chain execution and no production deployment.** This software does not guarantee profits.

## Wallet Connect V1.1

- Browser-side Wallet Standard discovery limited to Phantom and Solflare (mainnet). User must explicitly connect; no auto-connect or session persistence. Connection is not permission to trade.
- Separate `frontend/app/wallet-panel.tsx` and `frontend/lib/solana-readonly.mjs`: public address, SOL balance, legacy SPL Token and Token-2022 balances, read using HTTPS RPC. A failed request clears all displayed balances instead of showing stale/fake values.
- Mainnet public RPC default: `https://api.mainnet-beta.solana.com`; optional `NEXT_PUBLIC_SOLANA_RPC_URL` uses an HTTPS endpoint. Any `NEXT_PUBLIC_*` variable is public in the browser: never insert an API secret here.
- On Android, injected Wallet Standard providers appear inside a supporting wallet browser; opening a regular external Chrome tab may NOT find an installed wallet. No automatic deep links.
- The wallet section is entirely independent of the FastAPI/Paper Engine. No wallet address is sent to the trading backend. RPC providers do see the public address requested.
- The app only calls Wallet Standard `connect` and optional `disconnect`. It does not sign messages, transactions, or orders. The wallet itself controls connection approvals.

## Components

- `backend/app/market.py`: live DEX Screener boosted Solana tokens + token pairs; network errors fail closed.
- `backend/app/engine.py`: strict risk prefilters, 2% maximum stake, 3 simultaneous positions, simulated 0.5% slippage + 0.25% fees, persistent cash/positions/fills ledger (SQLite), chained SHA-256 evidence events.
- `backend/app/judge.py`: optional OpenAI-compatible AI advisory. Without configured HTTPS API, AI returns `WAIT` and **no buys occur**. Risk rules are mandatory regardless of AI response.
- `backend/app/main.py`: local FastAPI with manual tick, optional background paper tick (120s), -10% stop loss / +20% take profit, kill switch and proof integrity endpoint.
- `frontend`: Next.js responsive desktop + Android terminal in Polish. All balances and fills come from local API, not random animations.

## Local run (Python 3.12+, Node 22)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Manual **SKANUJ SOLANA** reads live market data; **PAPER TICK** evaluates positions and candidates. To allow optional AI advisory, configure `AI_API_URL`, `AI_API_KEY`, `AI_MODEL` before launching the backend. To run automatically, set `AUTO_PAPER=true` and use **one backend worker only**; default is disabled.

### Endpoints

`GET /api/health`, `GET /api/state`, `GET /api/scan`, `GET /api/proof`, `POST /api/paper/tick`, `POST /api/paper/halt`, `POST /api/paper/resume`.

### Tests

```bash
cd backend && python -m pytest -q
cd ../frontend && npm run test:wallet && npm run typecheck && npm run build
```

### Security / limitations

- **Never expose API publicly** as configured: no authentication; use localhost only. No backend endpoint signs or broadcasts Solana transactions.
- DEX Screener token boosts are promoted listings, **not investment recommendations**. Basic liquidity, age, volume and FDV checks are **not** contract audits. Mint authority, freeze authority, wallet concentration, honeypot conditions, wash trading and spoofed liquidity are **not** independently verified in V1.
- Simulated fills assume execution at market reference +/- fixed slippage + fee; real fill feasibility, MEV, swaps, taxes, market impact, latency and failed transactions are **not** modeled. Paper performance is not evidence of live trading profitability.
- No artificial prices, paper fills or balances. When network/AI fails, the system refuses to buy. Existing positions may remain open when quote feeds fail.
- Proof SHA-256 chain detects modifications inside the local event table, not tampering with the entire database or external financial settlement; external timestamping is not present.
- Stop-loss is checked only during ticks, not guaranteed execution. Halting freezes *all* paper orders, including sales. This is a simulation safety control, not a live exchange circuit breaker.
- Local SQLite is for single-instance V1 only; migrating to PostgreSQL and service authentication belongs to a later separately approved scope.

### Definition of Done

API health must return `PAPER_ONLY`; test `buy -> close -> evidence verified` must pass; API errors must not produce fabricated orders; frontend typecheck and build must succeed. Live data and profitability remain `UNKNOWN` until verified separately with a functioning external market feed and forward testing.

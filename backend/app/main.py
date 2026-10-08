"""Local-only paper trading API. No real order placement is implemented."""
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .engine import Ledger, evaluate
from .market import Market, MarketUnavailable
from .judge import judge

ledger = Ledger(os.getenv('PAPER_DB', './data/paper.sqlite3'))
market = Market()
_tick_lock = asyncio.Lock()


async def tick():
    if ledger.state()['halted']:
        return {'mode': 'PAPER_ONLY', 'outcomes': [], 'reason': 'HALTED'}
    if _tick_lock.locked():
        raise HTTPException(409, 'Tick już trwa')
    async with _tick_lock:
        try:
            candidates = await market.candidates()
            state = ledger.state()
            outcomes = []
            # Manage existing positions first; never close on stale or missing quotes.
            for position in state['positions']:
                try:
                    quote = await market.quote(position['token'], position['pair'])
                    change = quote.price / position['entry_price'] - 1
                    if change <= -0.10 or change >= 0.20:
                        outcomes.append(ledger.sell(quote))
                except MarketUnavailable:
                    outcomes.append({'executed': False, 'reason': 'POSITION_QUOTE_UNAVAILABLE', 'token': position['token']})
            if not ledger.state()['halted']:
                for pair in candidates:
                    decision = await judge(pair)
                    if decision['decision'] == 'BUY':
                        outcomes.append(ledger.buy(pair, source=decision['source']))
            return {'mode': 'PAPER_ONLY', 'scanned': len(candidates), 'outcomes': outcomes,
                    'rules': 'Obowiązkowe filtry + opcjonalny AI Judge; brak AI oznacza brak BUY'}
        except MarketUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc


async def automatic_loop():
    while True:
        try:
            await tick()
        except (HTTPException, MarketUnavailable):
            pass  # Never fabricate fills on upstream failures.
        await asyncio.sleep(max(60, int(os.getenv('PAPER_INTERVAL_SECONDS', '120'))))


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(automatic_loop()) if os.getenv('AUTO_PAPER', '').lower() == 'true' else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title='OSA Trading Desk', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv('FRONTEND_ORIGIN', 'http://localhost:3000')],
                   allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'PAPER_ONLY', 'onchain_enabled': False}


@app.get('/api/state')
def state():
    return ledger.state()


@app.get('/api/scan')
async def scan():
    try:
        pairs = await market.candidates()
        return {'source': 'DEXSCREENER_LIVE', 'mode': 'PAPER_ONLY', 'candidates': [
            {'pair': vars(p), 'assessment': evaluate(p)} for p in pairs]}
    except MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post('/api/paper/tick')
async def paper_tick():
    return await tick()


@app.post('/api/paper/halt')
def halt():
    ledger.set_halt(True)
    return {'halted': True}


@app.post('/api/paper/resume')
def resume():
    ledger.set_halt(False)
    return {'halted': False}


@app.get('/api/proof')
def proof():
    return {'verified': ledger.verify_evidence(), 'algorithm': 'SHA256_CHAIN',
            'scope': 'Local append-only event integrity, NOT blockchain settlement'}

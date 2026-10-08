"""Paper-only risk, ledger and execution. This package has NO wallet signing path."""
import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

INITIAL_CASH = 1000.0
FEE_RATE = 0.0025
SLIPPAGE_RATE = 0.005


@dataclass(frozen=True)
class Pair:
    token: str
    pair: str
    symbol: str
    price: float
    liquidity: float
    volume: float
    age_hours: float
    buys: int
    sells: int
    fdv: float
    url: str
    observed_at: int


def parse_pair(raw: dict[str, Any], now_ms: int | None = None) -> Pair:
    now_ms = now_ms or int(time.time() * 1000)
    created = raw.get('pairCreatedAt')
    created = float(created) if created is not None else 0
    age = (now_ms - created) / 3600000 if created > 0 else -1
    volume = raw.get('volume') or {}
    txns = (raw.get('txns') or {}).get('h24') or {}
    return Pair(
        token=str((raw.get('baseToken') or {}).get('address') or ''),
        pair=str(raw.get('pairAddress') or ''),
        symbol=str((raw.get('baseToken') or {}).get('symbol') or '?')[:24],
        price=float(raw.get('priceUsd') or 0),
        liquidity=float((raw.get('liquidity') or {}).get('usd') or 0),
        volume=float(volume.get('h24') or 0),
        age_hours=age,
        buys=int(txns.get('buys') or 0),
        sells=int(txns.get('sells') or 0),
        fdv=float(raw.get('fdv') or 0),
        url=str(raw.get('url') or ''),
        observed_at=now_ms // 1000,
    )


def evaluate(pair: Pair) -> dict[str, Any]:
    """Conservative pre-filter. Not an on-chain contract security audit."""
    checks = {
        'token_i_para': bool(pair.token and pair.pair),
        'cena': 0 < pair.price < 1e9,
        'plynnosc_min_25000': pair.liquidity >= 25000,
        'wolumen_24h_min_50000': pair.volume >= 50000,
        'wiek_pary_2h_min': pair.age_hours >= 2,
        'transakcje_24h_min_50': pair.buys + pair.sells >= 50,
        'fdv_do_plynnosci_max_30': 0 < pair.fdv <= pair.liquidity * 30,
    }
    score = round(sum(checks.values()) / len(checks) * 100)
    return {'accepted': all(checks.values()), 'score': score, 'checks': checks,
            'reason': 'Filtry wstępne PASS' if all(checks.values()) else 'Odrzucony przez filtr ryzyka'}


class Ledger:
    """SQLite transactions and hash-linked append-only event log; no real assets."""
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY CHECK(id=1), cash REAL NOT NULL, halted INTEGER NOT NULL);
            INSERT OR IGNORE INTO wallet VALUES (1, 1000.0, 0);
            CREATE TABLE IF NOT EXISTS positions (token TEXT PRIMARY KEY, pair TEXT NOT NULL, symbol TEXT NOT NULL,
              units REAL NOT NULL, spent REAL NOT NULL, entry_price REAL NOT NULL, opened_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER NOT NULL,
              side TEXT NOT NULL, token TEXT NOT NULL, symbol TEXT NOT NULL, units REAL NOT NULL,
              reference REAL NOT NULL, execution REAL NOT NULL, fee REAL NOT NULL, usd REAL NOT NULL,
              realized_pnl REAL, market_observed_at INTEGER NOT NULL, evidence_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER NOT NULL,
              kind TEXT NOT NULL, payload TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
            ''')

    def _db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _event(self, conn, kind: str, payload: dict) -> str:
        previous = conn.execute('SELECT hash FROM events ORDER BY id DESC LIMIT 1').fetchone()
        prev_hash = previous['hash'] if previous else 'GENESIS'
        timestamp = int(time.time())
        body = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        digest = hashlib.sha256(f'{prev_hash}|{timestamp}|{kind}|{body}'.encode()).hexdigest()
        conn.execute('INSERT INTO events (time,kind,payload,prev_hash,hash) VALUES (?,?,?,?,?)',
                     (timestamp, kind, body, prev_hash, digest))
        return digest

    def state(self) -> dict[str, Any]:
        with self.lock, self._db() as conn:
            wallet = conn.execute('SELECT * FROM wallet WHERE id=1').fetchone()
            positions = [dict(r) for r in conn.execute('SELECT * FROM positions ORDER BY opened_at DESC')]
            fills = [dict(r) for r in conn.execute('SELECT * FROM fills ORDER BY id DESC LIMIT 30')]
            events = [dict(r) for r in conn.execute('SELECT id,time,kind,prev_hash,hash FROM events ORDER BY id DESC LIMIT 20')]
            return {'mode': 'PAPER_ONLY', 'cash': round(wallet['cash'], 4),
                    'halted': bool(wallet['halted']), 'positions': positions, 'fills': fills,
                    'events': events, 'initial_cash': INITIAL_CASH,
                    'equity': None, 'equity_note': 'Wycena otwartych pozycji wymaga świeżych kwotowań'}

    def set_halt(self, halted: bool) -> None:
        with self.lock, self._db() as conn:
            conn.execute('UPDATE wallet SET halted=? WHERE id=1', (int(halted),))
            self._event(conn, 'HALT' if halted else 'RESUME', {'halted': halted})

    def buy(self, pair: Pair, source: str = 'RULES') -> dict[str, Any]:
        assessment = evaluate(pair)
        if not assessment['accepted']:
            return {'executed': False, 'reason': 'RISK_REJECT', 'assessment': assessment}
        if time.time() - pair.observed_at > 90 or pair.observed_at > time.time() + 10:
            return {'executed': False, 'reason': 'STALE_MARKET_DATA'}
        with self.lock, self._db() as conn:
            wallet = conn.execute('SELECT * FROM wallet WHERE id=1').fetchone()
            count = conn.execute('SELECT COUNT(*) c FROM positions').fetchone()['c']
            existing = conn.execute('SELECT token FROM positions WHERE token=?', (pair.token,)).fetchone()
            if wallet['halted']:
                return {'executed': False, 'reason': 'HALTED'}
            if count >= 3 or existing:
                return {'executed': False, 'reason': 'POSITION_LIMIT_OR_DUPLICATE'}
            # Cap stake at 2% of INITIAL cash per token, preventing compounding runaway exposure.
            budget = min(wallet['cash'] * 0.02, INITIAL_CASH * 0.02)
            if budget < 5:
                return {'executed': False, 'reason': 'INSUFFICIENT_CASH'}
            executed_price = pair.price * (1 + SLIPPAGE_RATE)
            fee = budget * FEE_RATE
            units = (budget - fee) / executed_price
            conn.execute('UPDATE wallet SET cash=cash-? WHERE id=1', (budget,))
            conn.execute('INSERT INTO positions VALUES (?,?,?,?,?,?,?)',
                         (pair.token, pair.pair, pair.symbol, units, budget, executed_price, int(time.time())))
            payload = {'side': 'BUY', 'token': pair.token, 'pair': pair.pair, 'reference': pair.price,
                       'execution': executed_price, 'units': units, 'usd': budget, 'fee': fee,
                       'source': source, 'market_observed_at': pair.observed_at, 'market_url': pair.url}
            digest = self._event(conn, 'PAPER_FILL', payload)
            conn.execute('''INSERT INTO fills (time,side,token,symbol,units,reference,execution,fee,usd,realized_pnl,market_observed_at,evidence_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (int(time.time()), 'BUY', pair.token, pair.symbol, units, pair.price, executed_price,
                          fee, budget, None, pair.observed_at, digest))
            return {'executed': True, 'side': 'BUY', 'token': pair.token, 'usd': round(budget, 2), 'evidence_hash': digest}

    def sell(self, pair: Pair) -> dict[str, Any]:
        if pair.price <= 0 or time.time() - pair.observed_at > 90 or pair.observed_at > time.time() + 10:
            return {'executed': False, 'reason': 'INVALID_OR_STALE_PRICE'}
        with self.lock, self._db() as conn:
            wallet = conn.execute('SELECT halted FROM wallet WHERE id=1').fetchone()
            if wallet['halted']:
                return {'executed': False, 'reason': 'HALTED'}
            pos = conn.execute('SELECT * FROM positions WHERE token=?', (pair.token,)).fetchone()
            if not pos or pos['pair'] != pair.pair:
                return {'executed': False, 'reason': 'NO_MATCHING_POSITION'}
            exec_price = pair.price * (1 - SLIPPAGE_RATE)
            gross = pos['units'] * exec_price
            fee = gross * FEE_RATE
            proceeds = gross - fee
            pnl = proceeds - pos['spent']
            conn.execute('UPDATE wallet SET cash=cash+? WHERE id=1', (proceeds,))
            conn.execute('DELETE FROM positions WHERE token=?', (pair.token,))
            payload = {'side': 'SELL', 'token': pair.token, 'pair': pair.pair, 'reference': pair.price,
                       'execution': exec_price, 'units': pos['units'], 'usd': proceeds,
                       'fee': fee, 'realized_pnl': pnl, 'market_observed_at': pair.observed_at, 'market_url': pair.url}
            digest = self._event(conn, 'PAPER_FILL', payload)
            conn.execute('''INSERT INTO fills (time,side,token,symbol,units,reference,execution,fee,usd,realized_pnl,market_observed_at,evidence_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (int(time.time()), 'SELL', pair.token, pair.symbol, pos['units'], pair.price,
                          exec_price, fee, proceeds, pnl, pair.observed_at, digest))
            return {'executed': True, 'side': 'SELL', 'token': pair.token, 'realized_pnl': round(pnl, 4), 'evidence_hash': digest}

    def verify_evidence(self) -> bool:
        previous = 'GENESIS'
        with self._db() as conn:
            for event in conn.execute('SELECT * FROM events ORDER BY id'):
                calculated = hashlib.sha256(f"{previous}|{event['time']}|{event['kind']}|{event['payload']}".encode()).hexdigest()
                if event['prev_hash'] != previous or event['hash'] != calculated:
                    return False
                previous = event['hash']
        return True

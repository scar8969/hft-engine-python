"""SQLite state store for the live engine — orders, trades, positions, equity, kill switch.

Everything the live engine does is journaled here so a restart can rebuild
positions/orders from disk instead of trusting memory. Thread-safe via a
single writer connection + WAL.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    filled_qty REAL DEFAULT 0,
    avg_fill REAL,
    latency_ms REAL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    qty REAL NOT NULL,
    avg_price REAL NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity (
    ts TEXT PRIMARY KEY,
    equity REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class StateStore:
    def __init__(self, db_path: str | Path = "hft_live.db"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=5)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    # ── orders ──────────────────────────────────────────────────────
    def upsert_order(self, order: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO orders (id, client_id, symbol, side, qty, price, status,
                                       created_at, updated_at, filled_qty, avg_fill, latency_ms, reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     status=excluded.status, updated_at=excluded.updated_at,
                     filled_qty=excluded.filled_qty, avg_fill=excluded.avg_fill,
                     latency_ms=excluded.latency_ms, reason=excluded.reason""",
                (order["id"], order.get("client_id"), order["symbol"], order["side"],
                 order["qty"], order.get("price"), order["status"],
                 order.get("created_at", _utc()), _utc(),
                 order.get("filled_qty", 0), order.get("avg_fill"),
                 order.get("latency_ms"), order.get("reason")),
            )
            self._conn.commit()

    def get_order(self, order_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def open_orders(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE status IN ('NEW','ACK','PARTIAL') ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def recent_orders(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── trades ──────────────────────────────────────────────────────
    def add_trade(self, symbol: str, side: str, qty: float, price: float,
                  order_id: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO trades (order_id, symbol, side, qty, price, ts) VALUES (?,?,?,?,?,?)",
                (order_id, symbol, side, qty, price, _utc()))
            self._conn.commit()

    def recent_trades(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── positions ───────────────────────────────────────────────────
    def set_position(self, symbol: str, qty: float, avg_price: float) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO positions (symbol, qty, avg_price, updated_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET
                     qty=excluded.qty, avg_price=excluded.avg_price, updated_at=excluded.updated_at""",
                (symbol, qty, avg_price, _utc()))
            self._conn.commit()

    def get_position(self, symbol: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None

    def all_positions(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM positions").fetchall()
        return [dict(r) for r in rows]

    # ── equity ──────────────────────────────────────────────────────
    def append_equity(self, equity: float) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO equity (ts, equity) VALUES (?,?)", (_utc(), equity))
            self._conn.commit()

    def equity_curve(self, limit: int = 500) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM equity ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ── meta / kill switch ──────────────────────────────────────────
    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
            self._conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_kill_switch(self, on: bool) -> None:
        self.set_meta("kill_switch", "1" if on else "0")

    def kill_switch(self) -> bool:
        return self.get_meta("kill_switch", "0") == "1"

    def snapshot(self) -> dict:
        """Full state snapshot for the dashboard."""
        return {
            "orders": self.recent_orders(),
            "trades": self.recent_trades(),
            "positions": self.all_positions(),
            "equity": self.equity_curve(),
            "kill_switch": self.kill_switch(),
            "started_at": self.get_meta("started_at"),
            "engine_state": self.get_meta("engine_state", "stopped"),
            "last_bar": json.loads(self.get_meta("last_bar", "null") or "null"),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

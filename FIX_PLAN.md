# HFT-Engine Fix Plan

Priority order. Each item = file, line, problem, fix.

---

## PHASE 1 — CRITICAL (crashes / wrong output)

### 1.1 `engine/order_manager.py:63` — finalize writes `symbol="?"`, `exit_time=None`
**Problem:** open position at end of backtest → synthetic trade has `symbol="?"` and `exit_time=None`.
`main.py:44` (`t.exit_time.date()`) and `dashboard.py:110` (`str(t.exit_time.date())`) crash with AttributeError.
CSV export gets wrong symbol.
**Fix:**
- Change `finalize(self, last_close)` → `finalize(self, last_close, symbol=None)` and use
  `symbol or self._open_entry` symbol (store symbol in `_open_entry` tuple at buy time).
- `_open_entry` is `(time, price, volume)` → make it `(time, price, volume, symbol)`.
- In `main.py:44` and `dashboard.py:110`, guard: `t.exit_time.date() if t.exit_time else "OPEN"`.
- `engine/__init__.py:37` → `self.orders.finalize(bars[-1].close, self.symbol)`.

### 1.2 `backtest.py:9-10` — `compute_metrics` returns `{}` on <2 bars → KeyError
**Problem:** `compare.py:46-48`, `heatmap.py:57`, `optimize.py:69` index `m['total_return_pct']` directly.
A 1-bar symbol → KeyError crash.
**Fix:** return a zero-filled dict instead of `{}`:
```python
if len(equities) < 2:
    return {"total_return_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe": 0.0,
            "trade_count": 0, "win_rate_pct": 0.0, "avg_win": 0.0,
            "avg_loss": 0.0, "final_equity": float(initial_capital)}
```

### 1.3 `heatmap.py:34,48` — momentum branch is a fake 2D grid
**Problem:** `x_name = y_name = "mom_period"` — both axes sweep the same param, y-axis values
ignored (`params = {"mom_period": xv}`). Output is a diagonal line, misleading.
**Fix:** sweep a real second param, e.g. `mom_period` (x) vs `threshold` (y):
```python
else:  # momentum
    x_name, y_name = "mom_period", "threshold"
    x_vals, y_vals = [20, 30, 50, 75, 100], [50, 100, 150, 200, 250]
    # in loop: params = {"mom_period": xv, "threshold": yv}
```

---

## PHASE 2 — LIVE FEED CORRECTNESS

### 2.1 `livefeed.py:90-92` — `depthUpdate` replaces whole book with deltas
**Problem:** `depthUpdate` events carry price/qty *changes*, but the code does
`self.depth["bids"] = data["b"]` — the ladder ends up with only the changed levels.
**Fix:** maintain a real book — apply deltas:
```python
def _apply_depth(self, side_key, updates):
    book = dict(self.depth[side_key])
    for p, q in updates:
        p, q = float(p), float(q)
        if q == 0: book.pop(p, None)
        else: book[p] = q
    self.depth[side_key] = sorted(book.items(), reverse=(side_key == "bids"))[:10]
```
Call with `data["b"]` / `data["a"]`. Seed with the `@depth20` snapshot first.

### 2.2 `livefeed.py:98-100` — duplicate stream assignment + dead code
**Problem:** `streams` assigned twice (first value lost); lines 93-95 unreachable
(snapshot has no `e` key → caught by the `if "e" not in data` branch at line 77).
**Fix:**
- Keep ONE stream string: `f"{sym}@trade/{sym}@depth20@100ms"` (diff) — or use `@depth20` snapshot only and drop the diff handling.
- Delete the dead `elif "bids" in data and "asks" in data:` block (lines 93-95).

---

## PHASE 3 — CLEANUP

### 3.1 Remove unused imports (pyflakes)
- `alpaca_bridge.py:11` — drop `from engine.models import MarketData`
- `api_server.py:20,21` — drop `threading`, `datetime`; `:118` use `except Exception:` (drop `as exc`)
- `footprint.py:102` — `im` unused → `ax.imshow(...)` without assignment
- `livefeed.py:17` — drop `defaultdict`
- `optimize.py:3,5` — drop `itertools`, `datetime`
- `portfolio.py:15` — drop `numpy as np`
- `engine/models.py:2` — drop `field`

### 3.2 Git housekeeping
- `git add api_server.py dashboard/ && git commit` — these are untracked.
- `fix_dashboard_scripts.py` + `stitch_prompt.txt` — decide: commit or delete.
  **Recommendation: DELETE `fix_dashboard_scripts.py`** — it re-injects the old
  fetch scripts that reference IDs no longer in the redesigned pages (the bug that
  caused "Unexpected token '<'"). It's a footgun.

### 3.3 Frontend ↔ backend contract
The redesigned dashboard is static demo — "Run Test" does nothing, and the dropdown
names (Trend Follower, Bounce Back…) don't match API keys (`sma`, `rsi`, `momentum`, `threshold`).
**Option A (recommended):** wire the new UI to `api_server.py`:
- add `id`s to inputs/result cards in `index.html`
- map friendly names → strategy keys in JS: `{Trend Follower: "sma", Bounce Back: "rsi", Momentum Rider: "momentum", Breakout Hunter: "threshold"}`
- `fetch("/api/backtest", ...)` on Run Test, fill KPIs + chart + trades table
- same for portfolio/orderflow/strategies pages
**Option B:** keep static, delete `api_server.py` or mark demo-only in README.

---

## PHASE 4 — CI HARDENING

### 4.1 `.github/workflows/ci.yml:18` — smoke test hits network + can crash
**Problem:** `python main.py --symbol AAPL ...` needs yfinance (network) in CI;
if the run ends with an open position, `main.py:44` crashes (issue 1.1).
**Fix:**
- After 1.1, add a `--no-plot` guard or wrap trade printing in try/except.
- Or replace the smoke test with an offline one: `python -c "from engine import HFTEngine; ..."` using a stubbed feed (like `tests/conftest.py` does).

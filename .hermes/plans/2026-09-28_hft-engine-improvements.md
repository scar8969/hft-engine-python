# HFT-Engine Improvement Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn hft-python from a working backtester into a complete, professional quant platform — real risk controls, realistic execution, richer analytics, multi-symbol live trading, and production packaging.

**Architecture:** Extend the existing event-driven engine (market_data → strategy → risk → order_manager) with: cash-aware risk validation, configurable position sizing, stop-loss/take-profit exits, richer metrics, Monte Carlo confidence bands, parallel walk-forward, multi-symbol live engine, and a proper CLI/package. Each change is TDD — failing test first, minimal implementation, verify, commit.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest (existing), yfinance (existing), skfolio (existing), concurrent.futures (stdlib), pyproject.toml + hatchling.

---

## Current Context (from audit)

- **61 tests pass** across `tests/` (engine, strategy, risk, order_manager, backtest, footprint, live).
- Engine: `engine/__init__.py` (HFTEngine), `engine/strategy.py` (4 strategies, **hardcoded volume=10**), `engine/order_manager.py` (**long-only**, fills at bar close), `engine/risk.py` (**no cash check**, only exposure + position cap), `engine/market_data.py` (yfinance).
- Metrics: `backtest.py::compute_metrics` returns **8 fields** (total_return, max_dd, sharpe, trade_count, win_rate, avg_win, avg_loss, final_equity).
- Live: `engine/live_engine.py` (single-symbol), `engine/broker.py` (dryrun/direct/alpaca), `engine/state.py` (SQLite), `engine/gateway.py` (binance ws / yfinance poll).
- CLI: `main.py` (`python main.py --symbol ...`), no pyproject.toml.
- API: `api_server.py` (13KB monolith, 5 endpoints + live singleton).

---

## Phase 0 — Baseline (verify current state)

### Task 0.1: Confirm baseline

**Files:** none

**Step 1:** Run `python -m pytest --tb=short -q` — expected: **61 passed**.

**Step 2:** Run `python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01` — expected: report prints, no crash.

**Step 3:** Commit nothing (baseline only).

---

## Phase 1 — Correctness (real bugs first)

### Task 1.1: Cash-sufficiency check in RiskManager

**Objective:** Reject BUY orders that exceed available cash (currently only checks exposure + position cap).

**Files:**
- Modify: `engine/risk.py:13-30` (`validate` signature)
- Modify: `engine/__init__.py:27-29` (`_on_signal` passes cash)
- Modify: `engine/order_manager.py` (expose `self.cash`)
- Test: `tests/test_risk.py`

**Step 1: Write failing test**

```python
def test_reject_buy_exceeding_cash(store_or_engine):
    # engine with $10k, order for 200 shares @ $100 = $20k
    # assert order rejected, reason mentions cash
```

**Step 2:** Run `pytest tests/test_risk.py -v` — expected: FAIL (no cash check yet).

**Step 3: Implement**

```python
# engine/risk.py
def validate(self, order: Order, current_position: int, cash: float = 0.0) -> bool:
    order_value = order.price * order.volume
    if order.side.value == "BUY" and cash > 0 and order_value > cash:
        order.status = OrderStatus.REJECTED
        order.reason = f"order value {order_value:.2f} > cash {cash:.2f}"
        self.rejected.append(order)
        return False
    # ... existing exposure + position checks
```

Wire cash through `HFTEngine._on_signal` → `self.orders.cash`.

**Step 4:** Run `pytest tests/test_risk.py -v` — expected: PASS.

**Step 5:** Commit `fix: reject buys exceeding available cash`.

### Task 1.2: Configurable position sizing (replace hardcoded volume=10)

**Objective:** Strategy emits signal with a size computed from capital/risk — not fixed 10.

**Files:**
- Modify: `engine/strategy.py:118-127` (`_emit` + `__init__`)
- Modify: `engine/__init__.py` (pass `qty` or `risk_pct`)
- Test: `tests/test_strategy.py`

**Step 1:** Test: strategy with `qty=25` emits orders with volume 25.

**Step 2:** Run — expected FAIL.

**Step 3:** Implement: add `self.qty = qty` param, `_emit` uses `self.qty`.

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: configurable order size`.

### Task 1.3: Short selling support

**Objective:** Allow SELL to open a short when flat (currently SELL with no position is a no-op).

**Files:**
- Modify: `engine/order_manager.py:26-51` (`place_order` SELL branch)
- Modify: `engine/risk.py` (position cap for shorts: `abs(cur_qty) + vol > max_position`)
- Test: `tests/test_order_manager.py`

**Step 1:** Test: flat → SELL 10 opens short position -10, cash increases.

**Step 2:** Run — expected FAIL (SELL with no `_open_entry` does nothing).

**Step 3:** Implement: SELL when `position == 0` opens short (track `_open_entry` with negative volume, cash += proceeds). SELL when `position > 0` closes long. BUY when `position < 0` closes short. BUY when flat opens long. Risk: `abs(cur_qty) + vol > max_position` for both sides.

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: short selling support`.

---

## Phase 2 — Backtest Realism

### Task 2.1: Stop-loss / take-profit / trailing stops

**Objective:** Orders carry exit levels; OrderManager checks them on each bar before strategy signals.

**Files:**
- Modify: `engine/models.py` (add `stop_loss`, `take_profit`, `trailing` to Order)
- Modify: `engine/order_manager.py` (check exits in `mark_to_market`)
- Modify: `engine/strategy.py` (emit orders with SL/TP from params)
- Test: `tests/test_order_manager.py`

**Step 1:** Test: buy @100 with SL 95, price drops to 94 → trade closed at ~95, loss recorded.

**Step 2:** Run — expected FAIL.

**Step 3:** Implement:
```python
# in mark_to_market, after equity update:
if self.position > 0 and self._open_entry:
    entry_p = self._open_entry[1]
    if self.stop_loss and close <= entry_p * (1 - self.stop_loss):
        self._force_close(timestamp, close, "stop_loss")
    elif self.take_profit and close >= entry_p * (1 + self.take_profit):
        self._force_close(timestamp, close, "take_profit")
```

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: stop-loss/take-profit exits`.

### Task 2.2: ATR-based position sizing

**Objective:** Size = `risk_amount / (ATR × multiplier)` instead of fixed shares.

**Files:**
- Modify: `engine/strategy.py` (compute ATR, size orders)
- Test: `tests/test_strategy.py`

**Step 1:** Test: high-ATR symbol → smaller position than low-ATR.

**Step 2:** Run — expected FAIL.

**Step 3:** Implement ATR(14) helper + `_size_position(close)`.

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: ATR position sizing`.

### Task 2.3: Intrabar execution (fill at high/low, not close)

**Objective:** BUY fills at `min(open, high)` with slippage; SELL at `max(open, low)` — realistic fills.

**Files:**
- Modify: `engine/order_manager.py:26-51` (`place_order` uses bar OHLC)
- Modify: `engine/__init__.py` (pass full bar, not just close)
- Test: `tests/test_order_manager.py`

**Step 1:** Test: BUY signal on a bar with open < close → fill price = open (not close).

**Step 2:** Run — expected FAIL (currently fills at close).

**Step 3:** Implement: `fill = order.side == BUY ? min(open, high) : max(open, low)` + slippage.

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: intrabar fills`.

---

## Phase 3 — Richer Analytics

### Task 3.1: Expand compute_metrics to 15+ fields

**Objective:** Add sortino, calmar, CAGR, profit factor, expectancy, alpha/beta, VaR, avg holding days.

**Files:**
- Modify: `backtest.py:34-41`
- Test: `tests/test_backtest.py`

**Step 1:** Test: metrics dict contains `sortino`, `calmar`, `cagr`, `profit_factor`, `expectancy`, `var_95`.

**Step 2:** Run — expected FAIL.

**Step 3:** Implement (all derived from existing equity_curve + trades):
```python
def _sortino(returns, rf): downside = returns[returns < 0]; return (mean - rf/252) / (downside.std() * sqrt(252)) if downside.std() else 0
def _calmar(returns, max_dd): return annualized_return / abs(max_dd) if max_dd else 0
def _cagr(equities, periods): return (equities[-1]/equities[0]) ** (252/periods) - 1
def _profit_factor(trades): gross_win / abs(gross_loss)
def _expectancy(trades): mean(pnl) - mean(costs)
def _var(returns, alpha=0.05): -np.percentile(returns, alpha*100)
```

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: 15+ backtest metrics`.

### Task 3.2: Monte Carlo confidence bands

**Objective:** Resample trade sequence N times → 5th/95th percentile equity bands (kills "lucky backtest" critique).

**Files:**
- Create: `montecarlo.py`
- Test: `tests/test_montecarlo.py`

**Step 1:** Test: `montecarlo.bootstrap(equity_curve, n=500)` returns `{p5, p50, p95}` arrays, p5 < p50 < p95.

**Step 2:** Run — expected FAIL (module missing).

**Step 3:** Implement:
```python
def bootstrap(equity_curve, n=500, seed=42):
    rng = np.random.default_rng(seed)
    rets = np.diff(equity) / equity[:-1]
    paths = []
    for _ in range(n):
        boot = rng.choice(rets, size=len(rets), replace=True)
        paths.append(equity[0] * np.cumprod(1 + boot))
    return {"p5": np.percentile(paths, 5, axis=0),
            "p50": np.percentile(paths, 50, axis=0),
            "p95": np.percentile(paths, 95, axis=0)}
```

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: monte carlo confidence bands`.

### Task 3.3: Parallel walk-forward optimization

**Objective:** Speed up `optimize.py` with `concurrent.futures` (embarrassingly parallel).

**Files:**
- Modify: `optimize.py:94-104` (param sweep loop)
- Test: `tests/test_optimize.py` (new)

**Step 1:** Test: `optimize.py` with 2 symbols returns same results as serial (determinism).

**Step 2:** Run — expected PASS (after impl).

**Step 3:** Implement:
```python
from concurrent.futures import ProcessPoolExecutor
with ProcessPoolExecutor() as ex:
    futures = {ex.submit(run_window, args.symbol, df, start, train_end, args.strategy, p, ...): p for p in grid}
    for fut in as_completed(futures):
        m = fut.result()
        # pick best
```

**Step 4:** Run — expected PASS + speedup.

**Step 5:** Commit `perf: parallel walk-forward`.

---

## Phase 4 — Live Engine

### Task 4.1: Multi-symbol live trading

**Objective:** LiveEngine manages N symbols, not 1.

**Files:**
- Modify: `engine/live_engine.py` (symbols list, per-symbol gateway/strategy/position)
- Modify: `engine/gateway.py` (multi-symbol binance stream)
- Modify: `api_server.py:_live` (accept symbols list)
- Test: `tests/test_live.py`

**Step 1:** Test: `LiveEngine(["AAPL","MSFT"], ...)` starts both gateways, positions tracked per symbol.

**Step 2:** Run — expected FAIL.

**Step 3:** Implement: `self.symbols`, `self.engines = {sym: StrategyEngine(...)}`, gateway fans out ticks.

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: multi-symbol live trading`.

### Task 4.2: Auto-kill on drawdown/daily-loss limit

**Objective:** Kill switch engages automatically when equity drops X% or daily loss exceeds Y.

**Files:**
- Modify: `engine/live_engine.py` (`_on_tick` checks equity)
- Test: `tests/test_live.py`

**Step 1:** Test: feed declining prices past threshold → `kill_switch()` True.

**Step 2:** Run — expected FAIL.

**Step 3:** Implement: track `peak_equity`, `day_start_equity`; if `equity < peak * (1 - max_dd)` or `equity < day_start * (1 - max_day_loss)` → `self.kill()`.

**Step 4:** Run — expected PASS.

**Step 5:** Commit `feat: auto-kill on drawdown limit`.

### Task 4.3: Alpaca order sync — poll to terminal state

**Objective:** Replace poll-once-then-ACK with poll-until-terminal (or websocket).

**Files:**
- Modify: `engine/broker.py:134-154` (`_submit_alpaca`)
- Test: `tests/test_live.py`

**Step 1:** Test: mocked alpaca returns "filled" on 2nd poll → order FILLED.

**Step 2:** Run — expected FAIL.

**Step 3:** Implement: loop up to 30s, break on filled/partially_filled/rejected/canceled/expired.

**Step 4:** Run — expected PASS.

**Step 5:** Commit `fix: alpaca poll to terminal state`.

---

## Phase 5 — Engineering / Packaging

### Task 5.1: pyproject.toml + CLI entry point

**Objective:** `pip install -e .` + `hft-engine` command.

**Files:**
- Create: `pyproject.toml`
- Modify: `main.py` (add `main()` return int, `if __name__` guard already there)

**Step 1:** Create pyproject:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "hft-engine"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = ["numpy", "pandas", "yfinance", "matplotlib", "skfolio", "websockets", "alpaca-py"]

[project.scripts]
hft-engine = "main:main"
hft-live = "live_engine:main"
```

**Step 2:** `pip install -e .` — expected: installs.

**Step 3:** `hft-engine --symbol AAPL` — expected: backtest runs.

**Step 4:** Commit `feat: pyproject + CLI`.

### Task 5.2: Replace print() with logging

**Files:**
- Modify: `engine/*.py`, `main.py`, `live_engine.py`, `api_server.py`

**Step 1:** Add `logging.basicConfig(level=INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")` in entry points.

**Step 2:** Replace `print(f"[live] ...")` → `logger.info(...)`.

**Step 3:** Run `python main.py --symbol AAPL` — expected: same output via logging.

**Step 4:** Commit `refactor: logging instead of print`.

### Task 5.3: Split api_server.py routes

**Objective:** Break 13KB monolith into `api/` package.

**Files:**
- Create: `api/__init__.py`, `api/backtest.py`, `api/portfolio.py`, `api/live.py`, `api/static.py`
- Modify: `api_server.py` → thin router

**Step 1:** Move each `_run_one`/`_portfolio`/`_strategies`/`_orderflow`/`_live` into its module.

**Step 2:** `api_server.py` imports + dispatches.

**Step 3:** Re-run all endpoint curls — expected: same responses.

**Step 4:** Commit `refactor: split api routes`.

### Task 5.4: SSE for live dashboard (replace 2s polling)

**Files:**
- Modify: `api_server.py` (add `/api/live/stream` SSE)
- Modify: `dashboard/live.html` (EventSource)

**Step 1:** Server: `text/event-stream` pushing `store.snapshot()` every 1s.

**Step 2:** Client: `new EventSource('/api/live/stream')` replaces `setInterval(refresh, 2000)`.

**Step 3:** Browser test — expected: live updates without polling.

**Step 4:** Commit `feat: SSE live stream`.

### Task 5.5: yfinance caching layer

**Files:**
- Modify: `engine/market_data.py`
- Create: `engine/cache.py`

**Step 1:** Cache `yf.download` results to `~/.hft_cache/{symbol}_{start}_{end}.parquet` (or CSV), TTL 1 day.

**Step 2:** `MarketDataHandler.connect()` checks cache first.

**Step 3:** Run backtest twice — second run hits cache (fast, no rate limit).

**Step 4:** Commit `feat: yfinance cache`.

---

## Phase 6 — Tests for untested surface

### Task 6.1: api_server endpoint tests

**Files:**
- Create: `tests/test_api.py`

**Step 1:** Test `/api/health` returns ok, `/api/backtest` returns metrics dict with expected keys.

**Step 2:** Run — expected PASS.

**Step 3:** Commit `test: api endpoints`.

### Task 6.2: optimize + montecarlo tests

**Files:**
- Create: `tests/test_optimize.py`, extend `tests/test_montecarlo.py`

**Step 1:** Test optimize determinism, montecarlo band ordering.

**Step 2:** Run — expected PASS.

**Step 3:** Commit `test: optimize + montecarlo`.

---

## Verification (final gate)

```bash
python -m pytest --tb=short -q          # expect: 75+ passed (was 61)
python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01   # backtest runs
python live_engine.py --symbol AAPL --backend dryrun --gateway poll  # live runs, Ctrl+C flattens
hft-engine --symbol AAPL                # CLI works after pip install -e .
curl -s http://127.0.0.1:8765/api/health  # API healthy
```

## Risks / Tradeoffs

- **Shorts (Task 1.3)** change PnL semantics — existing tests assert long-only behavior; update them deliberately.
- **Intrabar fills (Task 2.3)** will change backtest results (more realistic, slightly different numbers) — README numbers may need updating.
- **Multi-symbol live (Task 4.1)** increases API surface — keep single-symbol path as default.
- **ProcessPoolExecutor (Task 3.3)** — yfinance download in workers can hit rate limits; cache (Task 5.5) mitigates.
- **SSE (Task 5.4)** — ThreadingHTTPServer + SSE needs `Transfer-Encoding: chunked` handling; fallback to polling if flaky.

## Open Questions

- Should shorts be enabled by default or behind a flag? (Recommend: `allow_shorts=True` param, default False to preserve existing behavior.)
- ATR sizing: risk 1% per trade default? (Recommend: `risk_pct=0.01`.)
- Multi-symbol live: cap at 5 symbols for the free tier? (Recommend: yes, configurable.)

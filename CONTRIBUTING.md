# Contributing to HFT-Engine

Thanks for wanting to contribute! This project is small and deliberately simple — keep it that way.

## Getting started

1. Fork the repo
2. `git clone git@github.com:<you>/hft-engine-python.git`
3. `pip install -r requirements.txt`
4. Create a branch: `git checkout -b feat/your-feature`

## What we're looking for

- New strategies (momentum, breakout, mean-reversion variants)
- New data sources (databento, polygon, kraken websocket)
- Bug fixes with a failing test case
- Documentation / README improvements

## Code style

- Python 3.11+, type hints on public functions
- No new dependencies unless they earn their place
- Keep the event-driven architecture: market data → strategy → risk → order manager

## Testing

There's no formal test suite yet — run the CLI on a known symbol/period and confirm the output matches the README sample results:

```bash
python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01 --strategy sma
```

## Submitting

1. Push your branch
2. Open a PR against `main`
3. Describe what you changed and why, with sample output if it affects behavior

## Code of conduct

Be kind. No harassment, no spam, no fake contributions.

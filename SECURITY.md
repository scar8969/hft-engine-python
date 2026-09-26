# Security Policy

## Reporting a vulnerability

This is a research/educational project — no production systems depend on it. If you find a security issue:

1. **Do not open a public issue.**
2. Email `priyanshurout8969@gmail.com` with details.

## What's in scope

- Code execution vulnerabilities in the engine
- Data exfiltration via the data feeds (yfinance, Binance WebSocket)
- Anything that could compromise a user's machine

## Notes

- `alpaca_bridge.py` requires API keys via environment variables — never commit keys.
- The Binance WebSocket feed uses public endpoints only (no keys, no trading).

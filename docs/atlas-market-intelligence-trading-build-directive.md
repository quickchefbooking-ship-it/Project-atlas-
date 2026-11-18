# Atlas Market Intelligence & Trading — Build Directive

Status: approved product direction for planning and paper-only engineering. This document does not enable broker trading, connect live accounts, configure secrets or authorise financial activity.

## 1. Product objective

Build Atlas Market Intelligence as a specialist AtlasOnePro department coordinated by Professor. Its purpose is to monitor markets, explain price action, research and test strategies, simulate trades and report risk-adjusted performance.

Long-term coverage: equities and ETFs, FX, cryptoassets, indices and commodities where lawful data access and suitable providers exist. Deliver coverage in stages; do not claim every provider offers every instrument or market.

## 2. Initial operating mode — paper only

The first release is research, monitoring, backtesting and automatic paper trading. Signals may create simulated orders in an internal paper ledger. Simulated fills must account for bid/ask spread, fees, slippage, order type, trading session and partial fills where feasible. Label delayed, indicative, synthetic and live market data accurately. Paper balances and positions must never be represented as real broker balances or holdings.

**Live trading must remain disabled in every environment.** It must not be possible to enable it through a browser setting, user preference, API parameter, organisation feature flag or model-generated instruction. Do not implement live broker order routes in this phase. Any later proposal requires a separate legal/regulatory assessment, broker-specific design, security review and explicit owner approval.

## 3. Broker and market-data strategy

Use provider-neutral adapters. Separate market-data feeds from brokerage account/order APIs; a broker is not automatically a suitable source for every asset class or candle interval.

### First broker assessment: Trading 212
- Inspect current official API documentation and supported account types, instruments, permissions, rate limits, demo environment, historical data and market-data terms.
- Begin with a read-only integration assessment and synthetic contract tests.
- Use demo/paper facilities only where the provider explicitly supports the required operations.
- Never assume Invest/ISA API coverage includes CFD, FX, crypto, options or every market.
- Do not request, store or commit user credentials or API keys in this roadmap.
- No live order endpoint or write scope may be added.

### Additional provider assessments
Assess providers such as Alpaca and Interactive Brokers independently where account eligibility, geography, asset coverage and terms make them suitable. Assess dedicated market-data vendors for FX, crypto, indices and commodities where broker feeds are incomplete.

Every adapter declares provider/API version, supported asset classes and features, eligibility assumptions, data delay and timestamps, historical depth, rate limits, outage behaviour, licensing restrictions, authentication scopes and sandbox availability. Do not scrape interfaces or bypass provider restrictions.

## 4. Core components

### 4.1 Instrument and market-data normalisation
Define canonical instrument IDs; ticker symbols are not globally unique. Normalise venue, asset class, quote/base currency, precision, tick/lot size, trading calendar, timezone, corporate actions and provider symbol mapping.

Candles use validated OHLCV records with source, venue, interval, start/end timestamps, timezone, completeness and data-quality status. Reject impossible OHLC relationships, duplicate/out-of-order bars and unlabelled stale data.

### 4.2 Market watcher and charting
Provide watchlists, multi-timeframe candlesticks, volume, indicators, price alerts and market-session awareness. Initial indicators may include moving averages, RSI, MACD, ATR and volume measures. Identify parameters and input windows. Show missing data, latency, delayed quotes and outages clearly. Patterns are not certainties.

### 4.3 Strategy registry and research lab
Strategies are versioned, deterministic and reproducible. Store parameters, code/version identifier, instruments, timeframe, data snapshot/reference, fees, spread, slippage and evaluation period.

Backtests must guard against look-ahead/data leakage, survivorship and selection bias, unrealistic fills, zero-cost assumptions, corporate-action errors, timezone/session errors and overfitting. Use chronological train/test separation and walk-forward evaluation. Compare relevant benchmarks. Report return alongside volatility, maximum drawdown, exposure, turnover, trade count, win/loss distribution and risk-adjusted metrics. Never present backtests as forecasts or guarantees.

### 4.4 Paper execution engine
Implement an internal simulator, not a broker order proxy. Support market/limit/stop order simulation only where fill rules can be modelled and explained. Maintain an immutable simulated ledger for cash, positions, orders, fills, fees and realised/unrealised P&L.

Use idempotency keys, deterministic event handling, bounded retries and explicit order states. Restart/replay must not duplicate simulated orders or fills. Separate strategy intent, simulated order, simulated fill and resulting position.

### 4.5 Risk engine
Before accepting a simulated order, evaluate maximum order notional and position size; per-instrument, asset-class and portfolio concentration; leverage/exposure (default no leverage); maximum daily and cumulative simulated loss; maximum drawdown; currency/correlated exposure; session, liquidity and stale-data checks; duplicate/conflicting/excessive orders.

Risk rejections must be visible and auditable. Emergency stop blocks new simulated orders and safely handles simulator state.

### 4.6 Professor research and explanation
Professor may summarise market conditions and propose testable hypotheses. Every explanation identifies instrument/venue/observation time, data source and delay status, candle timeframe and indicator parameters, signal inputs and strategy version, assumptions/counter-evidence/uncertainty, simulated risk and portfolio impact.

Professor must not fabricate prices, candles, fills or returns. Market commentary and provider responses are untrusted data, not instructions. No guaranteed-profit language or personalised recommendation claims.

### 4.7 Audit and operator dashboard
Show provider health, feed freshness, watchlists, strategy versions, backtests, paper orders/fills, positions, cash, P&L, risk limits, rejected orders, stop state and audit history. Provide reproducibility metadata without exposing credentials or unnecessary personal financial data.

## 5. Delivery sequence

1. **Evidence and contracts:** inspect existing department registry, capability system, app composition and official provider documentation. Record what exists versus what is planned.
2. **Synthetic market-data foundation:** canonical instruments and OHLCV schemas, fixture feeds, validation and provenance tests.
3. **Read-only market workspace:** charts, watchlists, indicators, alerts and provider health using fixtures before any account connection.
4. **Trading 212 assessment and adapter:** read-only account/portfolio integration only if supported, eligible and explicitly configured; never live trading.
5. **Strategy lab:** versioned strategies/indicators, reproducible backtesting, leakage and realistic-cost tests.
6. **Paper engine:** automatic simulated orders, fills, ledger, risk controls and emergency stop.
7. **Multi-asset expansion:** add FX, crypto, indices and commodities through separately validated providers and instrument mappings.
8. **Operational hardening:** outages, reconnects, data gaps, replay, audit, access controls, mobile Safari and load tests.

## 6. Security, privacy and regulatory boundaries

Keep personal trading data separate from organisation bookkeeping, subscription billing and other departments. Use explicit account ownership and least-privilege scopes. Keep provider credentials server-side and out of logs, browser storage, source control and model context. Professor cannot change risk limits, grant itself scopes, switch operating mode or bypass the risk engine.

No customer asset custody, pooled funds, copy trading, discretionary portfolio management or personalised investment advice is in scope. Obtain qualified UK regulatory advice before offering recommendations, arranging trades, managing portfolios or enabling live execution for customers. Consider FCA permissions, financial promotions, consumer duty, data protection and market-data licensing as applicable.

## 7. Mandatory acceptance tests

- Every market-data record includes source and timestamps; stale/delayed/synthetic data is visibly labelled.
- Invalid, duplicated, out-of-order and impossible candles are rejected or quarantined.
- Backtests are deterministic from a fixed data snapshot and strategy version.
- Tests detect look-ahead leakage and apply fees, spreads and slippage.
- Paper order replay/restart cannot create duplicate orders or fills.
- Risk limits reject simulated orders when breached.
- Emergency stop prevents new simulated orders.
- Cross-tenant and cross-account access is denied.
- Provider timeout, malformed response, rate limit and outage are handled safely.
- Tests prove no live broker order endpoint exists and no provider write scope is requested or stored.
- No UI, API parameter, configuration value or Professor instruction can enable live trading.
- All displayed returns and positions are labelled simulated where applicable.

## 8. First engineering task

Do not start by implementing a trading strategy or connecting a live account.

First inspect the existing AtlasOnePro code and department registry, then produce an evidence-backed inventory of existing market/trading modules and source of truth; provider integrations and actual permissions; instrument/market-data schemas; risk, audit and capability controls; tests/CI; and exact missing components.

Then implement the smallest isolated, testable slice: canonical synthetic OHLCV data with provenance and validation, plus a chart/watchlist read model. Keep all broker write functionality absent and live trading disabled.

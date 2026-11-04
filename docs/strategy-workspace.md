# Private strategy workspace

`strategy.html` is the public login shell; strategy results are published only in `data/strategies.enc.json`. Other pages remain public. This GitHub Pages implementation decrypts content locally rather than providing a server session. It has no server-side rate limiting; anyone can download the ciphertext and attempt offline password guesses. Do not publish credentials, raw strategy reports, or API responses.

The single credential pair is held in GitHub Actions secrets `STRATEGY_LOGIN_USERNAME` and `STRATEGY_LOGIN_PASSWORD`; the Eastmoney skill credential is `MX_APIKEY`. Configure secrets via standard-input or a secure GitHub interface, never command arguments. The deployed page contains neither credentials nor the MX key. PBKDF2-SHA256 (600,000 iterations, random 32-byte salt) derives an AES-256-GCM key; every publication uses a fresh salt and 12-byte nonce. The username participates in key derivation. Decrypted contents and a nonextractable key material handle stay in memory; logout clears the report, reload requires login again. The strategy page runs only first-party code with a restrictive CSP and no third-party counters.

The `Daily strategy screen` workflow runs at 07:45 UTC on weekdays (15:45 China time, subject to GitHub scheduling delays), and supports manual dispatch. Non-trading days retain the previous report. Failure is visible as a failed Actions run and leaves the original encrypted snapshot/date intact. Its completion triggers the existing Pages publish workflow; this does not refresh other public market datasets.

The backend calls the official mx-xuangu stock-screen endpoint, shards code prefixes when a result exceeds 200, records interpreted conditions and coverage, then calls mx-data query for 40 trading sessions of real historical daily OHLCV and the historical limit-up status (minimum 35 aligned bars). This covers the longest 30-session strategy window without repeatedly requesting excessive history. Omitted entities are retried individually. A supplier quota exhaustion response stops immediately rather than becoming an empty pool; the existing encrypted report/date is retained, with the workflow reporting failure. Report fields include the session, generated timestamp, rule version, coverage, missing-data list, trigger ranges and invalidation levels. No fixed candidate quota, automatic watchlist changes, or trades.

The three views are: limit-up pullback recovery (20-session limit event, retreat, intact startup support, bullish recovery above MA10), second-board pullback (consecutive limit flags, 3–10 sessions after the break, volume <= half the break-day volume and MA10 support), and revised triple-volume (same-day >=3x preceding volume, bullish >3%, upper-half close, bottom-zone/real-body breakout tracking). Triple-volume has no hard moving-average alignment requirement. These are conservative daily-bar observation rules. Auction, sector strength and intraday VWAP acceptance are explicitly unverified; the page never labels daily bars alone as actionable buys.

The priority panel merges all strategy pools by code and keeps up to five mechanically ranked observations. It requires validated latest Eastmoney quote timestamps, excludes >=5% gain, <=-5% loss, broken guards, >8% guard distance and high-risk/unconfirmed-gap/signal-day patterns. Scores sum structure (30), distance to the trigger zone (25), guard distance (20), daily volume contraction (15), and current change (10); missing volume earns no volume points. A displayed score does not imply sector or intraday confirmation. All five can be absent. No portfolio or trading action follows this ranking.

Login automatically fetches current public Eastmoney quotes with CORS `fetch`; the real-time refresh button repeats it and recalculates ranking, while the separate snapshot button decrypts the latest MX daily report. Only Eastmoney's two quote hosts are allowed by `connect-src`; remote scripts/JSONP are prohibited on this page. No credentials are transmitted to quote endpoints and no decrypted results or quotes are persisted. Source timestamps are displayed independently of daily strategy dates. Intraday quotes more than ten minutes old, future timestamps, and missing fields cannot enter the current ranking. Outside trading hours the panel identifies the latest closing quote rather than claiming a live trade.

Local validation:

```sh
python scripts/test_strategy.py
node scripts/test_strategy_crypto.cjs
node scripts/test_strategy_ranking.cjs
node --check strategy.js
```

To refresh locally, write `--output` to an OS-private temporary directory outside this repo, then call `scripts/encrypt_strategy.cjs` using environment credentials. Never upload the plaintext or include it in Pages artifacts. Never cache private results in public Actions artifacts. Existing ciphertext in Git history remains decryptable with the corresponding old password if credentials are later changed; rotation cannot revoke copies already downloaded.

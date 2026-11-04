# Private strategy workspace

`strategy.html` is the public login shell; strategy results are published only in `data/strategies.enc.json`. Other pages remain public. This GitHub Pages implementation decrypts content locally rather than providing a server session. It has no server-side rate limiting; anyone can download the ciphertext and attempt offline password guesses. Do not publish credentials, raw strategy reports, or API responses.

The single credential pair is held in GitHub Actions secrets `STRATEGY_LOGIN_USERNAME` and `STRATEGY_LOGIN_PASSWORD`; the Eastmoney skill credential is `MX_APIKEY`. Configure secrets via standard-input or a secure GitHub interface, never command arguments. The deployed page contains neither credentials nor the MX key. PBKDF2-SHA256 (600,000 iterations, random 32-byte salt) derives an AES-256-GCM key; every publication uses a fresh salt and 12-byte nonce. The username participates in key derivation. Decrypted contents and a nonextractable key material handle stay in memory; logout clears the report, reload requires login again. The strategy page runs only first-party code with a restrictive CSP and no third-party counters.

The `Daily strategy screen` workflow runs at 07:45 UTC on weekdays (15:45 China time, subject to GitHub scheduling delays), and supports manual dispatch. Non-trading days retain the previous report. Failure is visible as a failed Actions run and leaves the original encrypted snapshot/date intact. Its completion triggers the existing Pages publish workflow; this does not refresh other public market datasets.

The backend calls the official mx-xuangu stock-screen endpoint, shards code prefixes when a result exceeds 200, records interpreted conditions and coverage, then calls mx-data query for real historical daily OHLCV and the historical limit-up status. Omitted entities are retried individually. Report fields include the session, generated timestamp, rule version, coverage, missing-data list, trigger ranges and invalidation levels. No fixed candidate quota, automatic watchlist changes, or trades.

The three views are: limit-up pullback recovery (20-session limit event, retreat, intact startup support, bullish recovery above MA10), second-board pullback (consecutive limit flags, 3–10 sessions after the break, volume <= half the break-day volume and MA10 support), and revised triple-volume (same-day >=3x preceding volume, bullish >3%, upper-half close, bottom-zone/real-body breakout tracking). Triple-volume has no hard moving-average alignment requirement. These are conservative daily-bar observation rules. Auction, sector strength and intraday VWAP acceptance are explicitly unverified; the page never labels daily bars alone as actionable buys.

Local validation:

```sh
python scripts/test_strategy.py
node scripts/test_strategy_crypto.cjs
node --check strategy.js
```

To refresh locally, write `--output` to an OS-private temporary directory outside this repo, then call `scripts/encrypt_strategy.cjs` using environment credentials. Never upload the plaintext or include it in Pages artifacts. Never cache private results in public Actions artifacts. Existing ciphertext in Git history remains decryptable with the corresponding old password if credentials are later changed; rotation cannot revoke copies already downloaded.

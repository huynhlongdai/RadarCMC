---
name: exit-radar-cmc
description: Use when an AI agent must (a) score DEX token exit/structure risk - liquidity structure, holder distribution, whale flow - or (b) call the CoinMarketCap API correctly. Carries Exit Radar's HTTP API, its 5-dimension 0-100 scoring model with level bands and colours, per-scan CMC credit costs, and the endpoint/plan traps found while building it. Load before writing code that hits Exit Radar (/api/scan, /api/search, /api/markets, /api/marketctx, /api/evidence, /api/calls, /api/tg, /api/cron/tick) or pro-api.coinmarketcap.com.
---

# Exit Radar + CoinMarketCap - agent operating skill

Exit Radar turns public CMC data into ONE 0-100 risk score per DEX token, with counters that only count
what was actually measured. This skill is the contract for agents that consume it or call CMC alongside it.

## 1. Two surfaces - pick the right one

| You want | Use | Never |
|---|---|---|
| A token's risk score with evidence | `GET <host>/api/scan?q=<symbol-or-contract>` | Re-deriving the score from raw CMC calls |
| A match list for a fuzzy query | `GET <host>/api/search?q=<text>` | Assuming exact symbol match |
| Market context for a headline | `GET <host>/api/marketctx` | Scraping CMC web pages |
| Raw counters behind one score | `GET <host>/api/evidence?q=<token>` | Guessing which dimensions were measured |
| CMC credit cost of a scan | `GET <host>/api/calls` | Estimating credits from memory |
| Direct market data | `https://pro-api.coinmarketcap.com/...` with a Pro key | `.../public-api/...` with a key (rejected) |

Host: run locally with `python3 exit_radar_server.py` (port 8787), or the Vercel deployment.
The single-file UI `exit-radar-app.html` talks to the same endpoints; it is the reference client.

## 2. Key handling (get this wrong and everything 401s)

Resolution order used by the server, first match wins:

1. request header `X-CMC-Key` (browser-entered, never stored server-side)
2. environment `CMC_API_KEY`
3. file `.data/cmc_key` (gitignored)

`GET /api/health` reports `keySource` and whether a key is present - call it first when debugging.
Rules:

- NEVER commit a CMC key. Repos here are public; `.env`, `.data/`, `.vercel/` are gitignored.
- Check remaining credits with `GET /v1/key/info` before a batch run.
- A Pro key must be sent to `/v1/...` (or `/v3/...`, `/v2/...`), NOT to `/public-api/...`.
  `/public-api/...` answers `401` with `error_code 1001` for every valid key; use it only keyless.

## 3. Scoring model (the only definition that matters)

Five dimensions, each 0-100, summed as `raw`, then normalised ON THE DIMENSIONS THAT APPLIED:

```
score = max(0, round(raw_sum / max_sum_of_applicable_dimensions * 100))
```

A dimension that cannot be measured is **excluded**, never counted as 0. Report the counters
(`dimsScored` / `dimsTotal`) beside the score - a 3/5 score is not comparable to a 5/5 score.

Level bands and the colours the UI uses (keep them when you render):

| Band | Score | Colour |
|---|---|---|
| LOW / THAP | 0-24 | `#16C784` |
| WATCH / DE MAT | 25-49 | `#EE8B2A` |
| HIGH / CAO | 50-74 | `#E4572E` |
| CRITICAL / NGHIEM TRONG | 75-100 | `#EA3943` |
| not applicable | - | muted |

Direction conventions in charts/tables: up/buy `#16C784`, down/sell `#EA3943`,
neutral series `--chart-a #5B8DEF` / `--chart-b #A78BFA`, brand `#3861FB`.

## 4. CMC endpoint reality (verified, not from docs)

Working with a Pro key: `v1/key/info`, `v1/cryptocurrency/info`, `v1/cryptocurrency/quotes/latest`,
`v1/cryptocurrency/quotes/historical`, `v3/fear-and-greed/latest`, `v1/altcoin-season-index/latest`,
`v1/global-metrics/quotes/historical`.

| Trap | Symptom | What to do instead |
|---|---|---|
| `public-api` + key | `401` `error_code 1001` | switch base to `pro-api` when a key exists |
| `v2/.../ohlcv/historical` | `403` `error_code 1006` | use `v1/cryptocurrency/quotes/historical` (daily close series) |
| `v1/dex/holders/trend/list` | `403` `1006` | no top-holder data: skip HHI/Gini/top-10, say so |
| `v1/dex/holders/list` | `500` "The system is busy" | retry later; do not fabricate holder tables |
| `trending/*` | `403` `1006` | build momentum from quotes/historical |
| `dex/search` | surprising hits | it matches SUBSTRINGS - verify the contract address |
| platform vs token id | wrong token | `pcid` = platform (Solana 5426), `cid` = token (BONK 23095) |
| `txId` field | misread as tx hash | it is CMC's internal id, not a transaction |
| "verified token" | does not exist | CMC has no verification flag; say "listed on CMC" instead |

Credit budget: one token scan costs roughly **8-14 credits**. On a 450,000-credit monthly plan that is
about 5 tokens every 10 minutes - a 5-minute cadence for 5 tokens exceeds the month. Always surface the
per-scan cost to the user and prefer longer intervals over silent overage.

## 5. Telegram alerting (optional surface)

- `GET /api/tg?action=status|code|push|test|preview|unlink` - status/code/test/unlink per chat
- `POST /api/telegram` - webhook, guarded by `X-Telegram-Bot-Api-Secret-Token`
- `GET /api/cron/tick?secret=...` - one scan pass, for a scheduler
- Rate limits are real: ~30 msg/s per bot, **1 msg/s per chat**, 20 msg/min per group. On `429` honour
  `parameters.retry_after`; the server already paces 1.1 s per chat and caps 18 msg/min per chat.
- Vercel Hobby crons run **once per day** with up to 59 minutes of drift - fine for a digest, useless for
  "alert me within minutes". Use a long-running `--bot` process for near-real-time.
- Bot messages rebuild the sentence from raw numbers per language (`/lang en|vi|zh`), so digits never
  drift between languages; units and level names are localised too.

## 6. Deploy checklist (Vercel)

1. Import the Git repo, Framework Preset **Other**, leave Build/Output empty.
2. Set `CMC_API_KEY` in project env vars.
3. Every endpoint needs a rewrite in `vercel.json` (`/api/search`, `/api/scan`, `/api/markets`,
   `/api/marketctx`, `/api/evidence`, `/api/calls`, `/api/tg`, `/api/cron/tick`, `/api/telegram`,
   `/api/health`) - a missing rewrite returns `404` even when the build succeeded.
4. `404 DEPLOYMENT_NOT_FOUND` on every path means the deployment no longer exists: re-import.

## 7. Anti-patterns

- Do not rebuild an MCP server around CMC - official MCP/CLI/Agent-Skills already exist; extend, do not duplicate.
- Do not present a score without its applicability counters and data provenance.
- Do not retry a `403/1006` endpoint with the same parameters; switch endpoint.
- Do not print or commit keys, and do not send a key to any third-party proxy.
- Do not translate digits: localise labels and units only (Vietnamese source strings, EN/ZH dictionaries,
  runtime DOM translation, `window.ER_I18N_EXTRA` for additions).

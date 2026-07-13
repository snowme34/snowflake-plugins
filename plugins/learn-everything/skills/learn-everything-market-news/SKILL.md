---
name: learn-everything-market-news
description: >
  Thin wrapper over learn-everything for daily stock/market-review videos. Give it a
  video URL and it produces Chinese learning notes: a top scannable watchlist table
  (ticker, bias, entry, stop, target, trigger, timeframe), next steps and per-scenario
  strategies, support levels and entry conditions, a catalyst/event calendar, broad-market
  context (SPX/QQQ/VIX, sector strength), and the dominant market narratives each tagged
  with its invalidation signal. Key chart frames extracted; output folder is date-stamped.
allowed-tools: Bash Read
argument-hint: <video-url> [extra hint text]
effort: high
---

Video URL (and any extra notes) to review: $ARGUMENTS

## Step 1: Parse

- `URL` — first token of $ARGUMENTS
- `EXTRA` — anything after the URL (optional; append to the hint below verbatim)

## Step 2: Get today's date

```bash
date +%F
```

Call the result `TODAY` (YYYY-MM-DD).

## Step 3: Invoke learn-everything

Invoke the `learn-everything` skill with this exact argument string:

```
URL --hint "这是股市盘后/盘前市场回顾(market review)。语言用中文。重点放在 'next steps' 以及不同情景下对应的不同策略。列出提到的 tickers,每个标的给出支撑位(support levels),以及买入 / 做空 / 其他操作各自的理想触发条件。提取关键图表的帧。把日期 TODAY 加到输出文件夹名的前缀,方便日后按日期查找。开头放一张速查表(标的 | 方向 | 进场 | 止损 | 目标 | 触发条件 | 周期),一眼扫完。单列一节列出催化剂与事件日历(财报日、CPI/FOMC 等宏观事件、个股新闻)。给出大盘背景:SPX/QQQ/VIX 的关键位与风险偏好(risk-on/off)、板块强弱。再单列一节梳理近期重大市场叙事(recent mega market stories / 主导叙事),每个叙事写明'失效信号'——即什么价格或事件一旦出现就说明该叙事不再成立,方便日后逐条核对。EXTRA" --video-frame-hint --lang Chinese
```

Substitute `URL`, `TODAY`, and `EXTRA` with their real values. If there is no EXTRA, drop it.

## Step 4: Print completion

Relay the output path that learn-everything reports.

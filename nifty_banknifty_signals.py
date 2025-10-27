# nifty_banknifty_signals.py
# Signals: EMA/VWAP/ADX/Volume + ATR sizing
# Logs to signal_log.csv and computes historical win% (Option 2)
# Sends Telegram messages for BUY/SELL signals and manual-run confirmations

import os
import time
import math
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import ta
import pytz
from datetime import datetime, timezone, timedelta

# ---------------- CONFIG ----------------
CSV_FILE = "signal_log.csv"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ENV = "TELEGRAM_CHAT_ID"

MARKET_TZ = pytz.timezone("Asia/Kolkata")
MARKET_OPEN = (9, 15)     # 09:15 IST
MARKET_CLOSE = (15, 30)   # 15:30 IST

# thresholds & multipliers
ADX_THRESHOLD = 25
VOLUME_MULT = 1.2
ATR_SL_MULT = 1.2
ATR_TGT_MULT = 2.5

# historical confidence params
MIN_HISTORY_FOR_CONFIDENCE = 5     # minimum past signals required to compute a meaningful win%
MAX_HISTORY_LOOKBACK_DAYS = 365    # consider at most this many days in history

# polite sleep between API calls to avoid rate limits
SLEEP_BETWEEN_SYMBOLS = 0.25

# ---------------- HELPERS ----------------
def now_ist():
    return datetime.now(timezone.utc).astimezone(MARKET_TZ)

def is_market_open():
    n = now_ist()
    if n.weekday() >= 5:  # Sat=5, Sun=6
        return False
    open_dt = n.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    close_dt = n.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return open_dt <= n <= close_dt

def send_telegram_message(text):
    token = os.getenv(TELEGRAM_TOKEN_ENV)
    chat_id = os.getenv(TELEGRAM_CHAT_ENV)
    if not token or not chat_id:
        print("Telegram credentials missing; cannot send message.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        print("Telegram status:", r.status_code)
        return r.status_code == 200
    except Exception as e:
        print("Telegram send error:", e)
        return False

def ensure_csv():
    """Create CSV with required columns if missing; otherwise ensure columns exist."""
    cols = ["timestamp","symbol","strategy","direction","entry","SL","TGT","status","resolved_at","result"]
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=cols)
        df.to_csv(CSV_FILE, index=False)
        print("Created signal_log.csv with headers.")
        return
    try:
        df = pd.read_csv(CSV_FILE)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            for c in missing:
                df[c] = ""
            df.to_csv(CSV_FILE, index=False)
            print("Added missing columns to signal_log.csv:", missing)
    except Exception as e:
        print("Error reading CSV; recreating:", e)
        df = pd.DataFrame(columns=cols)
        df.to_csv(CSV_FILE, index=False)

def fetch_ohlc(symbol, period="15d", interval="15m"):
    """Fetch OHLCV from yfinance, flatten MultiIndex if needed and coerce numeric."""
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
    except Exception as e:
        print("yfinance download error for", symbol, e)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    for col in ["Open","High","Low","Close","Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(how="all")
    return df

def session_vwap(df):
    """Returns running VWAP series for intraday df (typical price * vol cumulative / vol cumulative)."""
    if df.empty or not all(c in df.columns for c in ["High","Low","Close","Volume"]):
        return pd.Series(index=df.index, data=np.nan)
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = tp * df["Volume"]
    cum_pv = pv.cumsum()
    cum_vol = df["Volume"].cumsum().replace({0: np.nan})
    return cum_pv / cum_vol

# ---------------- INDICATOR-BASED RULES ----------------
def intraday_rule(symbol):
    """Run 15m checks and return tuple (direction, entry, SL, TGT, matched_indicators) or None."""
    df = fetch_ohlc(symbol, period="15d", interval="15m")
    if df.empty or len(df) < 30:
        return None

    # indicators
    df["EMA20"] = ta.trend.EMAIndicator(df["Close"], window=20).ema_indicator()
    df["EMA50"] = ta.trend.EMAIndicator(df["Close"], window=50).ema_indicator()
    df["ADX"] = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=14).adx()
    df["ATR"] = ta.volatility.AverageTrueRange(df["High"], df["Low"], df["Close"], window=14).average_true_range()
    df["RSI"] = ta.momentum.RSIIndicator(df["Close"], window=14).rsi()
    df["VWAP"] = session_vwap(df)
    df["VOL_SMA20"] = df["Volume"].rolling(20).mean()

    if len(df) < 4:
        return None

    latest = df.iloc[-2]   # use last completed candle
    prev = df.iloc[-3]

    price = float(latest["Close"])
    atr = float(latest["ATR"]) if not np.isnan(latest["ATR"]) else None
    vwap = float(latest["VWAP"]) if not np.isnan(latest["VWAP"]) else None
    adx_val = float(latest["ADX"]) if not np.isnan(latest["ADX"]) else 0
    vol_now = float(latest["Volume"])
    vol_avg = float(latest["VOL_SMA20"]) if not np.isnan(latest["VOL_SMA20"]) else 0

    matched = []
    # EMA crossover
    if prev["EMA20"] <= prev["EMA50"] and latest["EMA20"] > latest["EMA50"]:
        matched.append("EMA_cross_up")
    if prev["EMA20"] >= prev["EMA50"] and latest["EMA20"] < latest["EMA50"]:
        matched.append("EMA_cross_down")
    # VWAP bias
    if vwap and price > vwap:
        matched.append("Price>VWAP")
    if vwap and price < vwap:
        matched.append("Price<VWAP")
    # ADX strength
    if adx_val >= ADX_THRESHOLD:
        matched.append("ADX_ok")
    # Volume confirmation
    if vol_avg and vol_now > VOLUME_MULT * vol_avg:
        matched.append("Vol_ok")
    # RSI filter
    if latest["RSI"] < 40:
        matched.append("RSI_oversold")
    if latest["RSI"] > 60:
        matched.append("RSI_overbought")

    # decide
    # BUY: EMA_cross_up + Price>VWAP + ADX_ok (+ Vol_ok preferred)
    buy_cond = ("EMA_cross_up" in matched) and ("Price>VWAP" in matched) and ("ADX_ok" in matched)
    sell_cond = ("EMA_cross_down" in matched) and ("Price<VWAP" in matched) and ("ADX_ok" in matched)

    if buy_cond and atr and atr > 0:
        sl = price - ATR_SL_MULT * atr
        tgt = price + ATR_TGT_MULT * atr
        indicators = matched
        return ("BUY", price, sl, tgt, indicators)
    if sell_cond and atr and atr > 0:
        sl = price + ATR_SL_MULT * atr
        tgt = price - ATR_TGT_MULT * atr
        indicators = matched
        return ("SELL", price, sl, tgt, indicators)

    return None

def swing_rule(symbol):
    """60m swing logic using EMA50/200 + ADX + ATR + volume."""
    df = fetch_ohlc(symbol, period="6mo", interval="60m")
    if df.empty or len(df) < 200:
        return None

    df["EMA50"] = ta.trend.EMAIndicator(df["Close"], window=50).ema_indicator()
    df["EMA200"] = ta.trend.EMAIndicator(df["Close"], window=200).ema_indicator()
    df["ADX"] = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=14).adx()
    df["ATR"] = ta.volatility.AverageTrueRange(df["High"], df["Low"], df["Close"], window=14).average_true_range()
    df["VOL_SMA20"] = df["Volume"].rolling(20).mean()

    latest = df.iloc[-2]
    prev = df.iloc[-3]
    price = float(latest["Close"])
    atr = float(latest["ATR"]) if not np.isnan(latest["ATR"]) else None
    adx_val = float(latest["ADX"]) if not np.isnan(latest["ADX"]) else 0
    vol_now = float(latest["Volume"])
    vol_avg = float(df["VOL_SMA20"].iloc[-2]) if not np.isnan(df["VOL_SMA20"].iloc[-2]) else 0

    matched = []
    if prev["EMA50"] <= prev["EMA200"] and latest["EMA50"] > latest["EMA200"]:
        matched.append("EMA50_cross_up")
    if prev["EMA50"] >= prev["EMA200"] and latest["EMA50"] < latest["EMA200"]:
        matched.append("EMA50_cross_down")
    if adx_val >= ADX_THRESHOLD:
        matched.append("ADX_ok")
    if vol_avg and vol_now > VOLUME_MULT * vol_avg:
        matched.append("Vol_ok")

    buy_cond = ("EMA50_cross_up" in matched) and ("ADX_ok" in matched)
    sell_cond = ("EMA50_cross_down" in matched) and ("ADX_ok" in matched)

    if buy_cond and atr and atr > 0:
        sl = price - ATR_SL_MULT * atr
        tgt = price + ATR_TGT_MULT * atr
        return ("BUY", price, sl, tgt, matched)
    if sell_cond and atr and atr > 0:
        sl = price + ATR_SL_MULT * atr
        tgt = price - ATR_TGT_MULT * atr
        return ("SELL", price, sl, tgt, matched)
    return None

# ---------------- SIGNAL LOG / UPDATE / HISTORICAL CONFIDENCE ----------------
def record_signal(symbol, strategy, direction, entry, sl, tgt):
    ensure_csv()
    df = pd.read_csv(CSV_FILE)
    ts = now_ist().strftime("%Y-%m-%d %H:%M:%S%z")
    row = {
        "timestamp": ts,
        "symbol": symbol,
        "strategy": strategy,
        "direction": direction,
        "entry": round(entry, 2),
        "SL": round(sl, 2),
        "TGT": round(tgt, 2),
        "status": "PENDING",
        "resolved_at": "",
        "result": ""
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)
    print("Recorded signal:", symbol, strategy, direction, entry)

def update_pending_signals():
    """Check pending signals and mark them as TGT/SL if hit in historical available candles."""
    if not os.path.exists(CSV_FILE):
        return
    df = pd.read_csv(CSV_FILE)
    if "status" not in df.columns:
        ensure_csv()
        df = pd.read_csv(CSV_FILE)
    pending_idx = df[df["status"] == "PENDING"].index.tolist()
    if not pending_idx:
        return
    for idx in pending_idx:
        row = df.loc[idx]
        symbol = row["symbol"]
        strat = row.get("strategy", "INTRADAY")
        direction = row["direction"]
        sl = float(row["SL"])
        tgt = float(row["TGT"])
        # choose proper timeframe to look forward
        if strat.upper() == "INTRADAY":
            df_ohlc = fetch_ohlc(symbol, period="7d", interval="15m")
        else:
            df_ohlc = fetch_ohlc(symbol, period="90d", interval="60m")
        if df_ohlc.empty:
            continue
        hit = None
        for _, candle in df_ohlc.iterrows():
            high = float(candle.get("High", math.nan))
            low = float(candle.get("Low", math.nan))
            if direction == "BUY":
                if high >= tgt:
                    hit = "TGT"; break
                if low <= sl:
                    hit = "SL"; break
            else:
                if low <= tgt:
                    hit = "TGT"; break
                if high >= sl:
                    hit = "SL"; break
        if hit:
            df.at[idx, "status"] = hit
            df.at[idx, "resolved_at"] = now_ist().strftime("%Y-%m-%d %H:%M:%S%z")
            df.at[idx, "result"] = "WIN" if hit == "TGT" else "LOSS"
            print(f"Updated {symbol} signal idx {idx} -> {hit}")
    df.to_csv(CSV_FILE, index=False)

def compute_historical_confidence(symbol, direction):
    """
    Compute win% for similar historical signals:
      - filters CSV for same symbol and same direction (BUY/SELL)
      - considers last MAX_HISTORY_LOOKBACK_DAYS
      - requires MIN_HISTORY_FOR_CONFIDENCE records to return a %,
        otherwise returns None to indicate insufficient data
    """
    if not os.path.exists(CSV_FILE):
        return None
    df = pd.read_csv(CSV_FILE)
    if df.empty:
        return None
    # filter by symbol and direction, exclude PENDING
    df["timestamp_parsed"] = pd.to_datetime(df["timestamp"], errors="coerce")
    cutoff = now_ist() - timedelta(days=MAX_HISTORY_LOOKBACK_DAYS)
    df_recent = df[(df["symbol"] == symbol) & (df["direction"] == direction) & (df["timestamp_parsed"] >= cutoff)]
    df_resolved = df_recent[df_recent["status"].isin(["TGT","SL"])]
    total = len(df_resolved)
    if total < MIN_HISTORY_FOR_CONFIDENCE:
        return None
    wins = len(df_resolved[df_resolved["status"] == "TGT"])
    winpct = round((wins / total) * 100, 2)
    return winpct

# ---------------- MESSAGE FORMATTING ----------------
def format_signal_message(symbol, direction, entry, sl, tgt, indicators, winpct):
    now_str = now_ist().strftime("%Y-%m-%d %H:%M IST")
    # percentages for TGT/SL relative to entry
    def pct(x):
        return round((x - entry) / entry * 100, 2)
    tgt_pct = pct(tgt)
    sl_pct = pct(sl)
    lines = [
        f"*{direction} SIGNAL* — `{symbol}`",
        f"Time: {now_str}",
        f"Entry: {entry:.2f}",
        f"Target: {tgt:.2f} ({'+' if tgt_pct>=0 else ''}{tgt_pct}%)",
        f"Stop Loss: {sl:.2f} ({'' if sl_pct<0 else '+'}{sl_pct}%)",
        f"Win Probability (history): {winpct if winpct is not None else 'Insufficient data'}",
        "",
        f"Indicators: {', '.join(indicators) if indicators else 'N/A'}",
    ]
    return "\n".join(lines)

# ---------------- SYMBOL LISTS ----------------
NIFTY50 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS", "HINDUNILVR.NS",
    "ITC.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "HCLTECH.NS", "ASIANPAINT.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "NESTLEIND.NS",
    "WIPRO.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS", "TATAMOTORS.NS",
    "GRASIM.NS", "BAJAJFINSV.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS",
    "BPCL.NS", "HEROMOTOCO.NS", "HINDALCO.NS", "TECHM.NS", "JSWSTEEL.NS",
    "CIPLA.NS", "DRREDDY.NS", "BRITANNIA.NS", "DIVISLAB.NS", "EICHERMOT.NS",
    "SBILIFE.NS", "BAJAJ-AUTO.NS", "TATACONSUM.NS", "APOLLOHOSP.NS",
    "TATASTEEL.NS", "UPL.NS", "INDUSINDBK.NS", "HDFCLIFE.NS", "ICICIPRULI.NS",
    "LTIM.NS", "DMART.NS"
]

BANKNIFTY = [
    "HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","AXISBANK.NS","SBIN.NS","INDUSINDBK.NS"
]

SYMBOLS = list(dict.fromkeys(NIFTY50 + BANKNIFTY))

# ---------------- MAIN ----------------
def main():
    ensure_csv()
    # only run heavy checks in market hours; allow manual runs to still send confirmation
    if not is_market_open() and os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("Market closed and not a manual run — exiting.")
        return

    # first update any pending signals with available OHLC
    update_pending_signals()

    found_messages = []
    new_signals = 0

    for sym in SYMBOLS:
        try:
            # intraday
            res = intraday_rule(sym)
            if res:
                direction, entry, sl, tgt, indicators = res
                # compute historical confidence
                hist_conf = compute_historical_confidence(sym, direction)
                # fallback: if insufficient history, show "Insufficient data"
                record_signal(sym, "INTRADAY", direction, entry, sl, tgt)
                msg = format_signal_message(sym, direction, entry, sl, tgt, indicators, hist_conf)
                found_messages.append(msg)
                new_signals += 1
                time.sleep(SLEEP_BETWEEN_SYMBOLS)

            # swing
            res2 = swing_rule(sym)
            if res2:
                direction, entry, sl, tgt, indicators = res2
                hist_conf = compute_historical_confidence(sym, direction)
                record_signal(sym, "SWING", direction, entry, sl, tgt)
                msg = format_signal_message(sym, direction, entry, sl, tgt, indicators, hist_conf)
                found_messages.append(msg)
                new_signals += 1
                time.sleep(SLEEP_BETWEEN_SYMBOLS)

        except Exception as e:
            print("Error processing", sym, e)
            continue

    # Re-run update to mark signals that may have been immediately hit
    update_pending_signals()

    # recompute accuracy summary
    accuracy, total, achieved, failed, pending = compute_overall_accuracy_summary()

    # Send messages if we found any new signals
    if new_signals > 0:
        header = f"📊 *NIFTY / BANKNIFTY Signals* ({now_ist().strftime('%Y-%m-%d %H:%M')})\n"
        footer = f"\n\n📈 Historical Accuracy: {accuracy}% | Total:{total} | Wins:{achieved} | Losses:{failed} | Pending:{pending}"
        full_msg = header + "\n\n---\n\n".join(found_messages) + footer
        send_telegram_message(full_msg)
        print("Sent", new_signals, "signal messages.")
    else:
        print("No new signals this cycle.")
        # Optionally send a small confirmation only on manual run
        if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
            send_telegram_message(f"✅ Manual run complete — no new signals ({now_ist().strftime('%Y-%m-%d %H:%M')}).")

# ---------------- SUMMARY / ACCURACY ----------------
def compute_overall_accuracy_summary():
    """Return (accuracy_pct, total, wins, losses, pending)."""
    if not os.path.exists(CSV_FILE):
        return 0.0, 0, 0, 0, 0
    df = pd.read_csv(CSV_FILE)
    total = len(df)
    if total == 0:
        return 0.0, 0, 0, 0, 0
    wins = len(df[df["status"] == "TGT"])
    losses = len(df[df["status"] == "SL"])
    pending = len(df[df["status"] == "PENDING"])
    accuracy = round((wins / total * 100) if total > 0 else 0.0, 2)
    return accuracy, total, wins, losses, pending

# ---------------- ENTRY POINT ----------------
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Fatal error in main:", e)
        # If manually triggered, also notify
        if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
            send_telegram_message(f"❌ Bot error during manual run: {e}")

# nifty_banknifty_signals.py
# Final signal engine — EMA + VWAP + ADX + Volume + ATR rules
# Intraday: 15m candles (EMA20/50 crossover) + VWAP/ADX/Vol filters
# Swing: 60m candles (EMA50/200 crossover) + ADX/Vol filters
# SL = 1.2 * ATR, TGT = 2.5 * ATR
# Sends Telegram only during market hours and only when signals occur
# Persists signal history in signal_log.csv and updates status (PENDING/TGT/SL)

import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import ta
import pytz
from datetime import datetime, timezone

# ---------------- CONFIG ----------------
CSV_FILE = "signal_log.csv"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ENV = "TELEGRAM_CHAT_ID"

# ATR multipliers
ATR_SL_MULT = 1.2
ATR_TGT_MULT = 2.5

# ADX threshold and volume multiplier
ADX_THRESHOLD = 25
VOLUME_MULT = 1.2

# Market hours IST
MARKET_TZ = pytz.timezone("Asia/Kolkata")
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MIN = 30

# Sleep between symbol requests to avoid rate limits
SLEEP_BETWEEN = 0.25

# ---------------- SYMBOL LISTS ----------------
# NIFTY50 (subset typical — expand if you want full exact)
NIFTY50 = [
    "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","LT.NS","SBIN.NS","AXISBANK.NS","HINDUNILVR.NS",
    "ITC.NS","BAJFINANCE.NS","BHARTIARTL.NS","HCLTECH.NS","ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS","TITAN.NS","ULTRACEMCO.NS","NESTLEIND.NS",
    "WIPRO.NS","POWERGRID.NS","NTPC.NS","ONGC.NS","TATAMOTORS.NS","GRASIM.NS","BAJAJFINSV.NS","ADANIENT.NS","ADANIPORTS.NS","COALINDIA.NS",
    "BPCL.NS","HEROMOTOCO.NS","HINDALCO.NS","TECHM.NS","JSWSTEEL.NS","CIPLA.NS","DRREDDY.NS","BRITANNIA.NS","DIVISLAB.NS","EICHERMOT.NS",
    "SBILIFE.NS","BAJAJ-AUTO.NS","TATACONSUM.NS","APOLLOHOSP.NS","TATASTEEL.NS","UPL.NS","INDUSINDBK.NS","HDFCLIFE.NS","LTIM.NS","DMART.NS"
]

# BANK NIFTY (typical major bank symbols; ensure these match your data source)
BANKNIFTY = [
    "HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","AXISBANK.NS","SBIN.NS","INDUSINDBK.NS","YESBANK.NS","BANKBARODA.NS","PNB.NS","FEDERALBNK.NS"
]

SYMBOLS = list(dict.fromkeys(NIFTY50 + BANKNIFTY))  # deduplicate while preserving order

# ---------------- HELPERS ----------------
def is_market_open(now_utc=None):
    """Return True if current IST time is Mon-Fri between 09:15 and 15:30."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(MARKET_TZ)
    if now_ist.weekday() >= 5:
        return False
    open_time = now_ist.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0)
    close_time = now_ist.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN, second=0, microsecond=0)
    return open_time <= now_ist <= close_time

def send_telegram_message(text):
    token = os.getenv(TELEGRAM_TOKEN_ENV)
    chat_id = os.getenv(TELEGRAM_CHAT_ENV)
    if not token or not chat_id:
        print("Telegram credentials missing.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        print("Telegram status:", r.status_code, r.text)
        return r.status_code == 200
    except Exception as e:
        print("Telegram exception:", e)
        return False

def fetch_ohlc(symbol, period="15d", interval="15m"):
    """Fetch OHLCV and flatten columns from yfinance."""
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
    except Exception as e:
        print("yfinance error for", symbol, e)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    # ensure numeric
    for col in ["Close", "High", "Low", "Open", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(how="all")

def session_vwap(df):
    """Compute running session VWAP for dataframe (assumes df is intraday and sorted)."""
    # typical price * volume cumulative / volume cumulative
    df = df.copy()
    if "High" not in df.columns or "Low" not in df.columns or "Close" not in df.columns or "Volume" not in df.columns:
        return pd.Series(index=df.index, data=np.nan)
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = typical * df["Volume"]
    cum_pv = pv.cumsum()
    cum_vol = df["Volume"].cumsum()
    vwap = cum_pv / cum_vol.replace({0: np.nan})
    return vwap

def ensure_csv():
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=["timestamp","symbol","strategy","direction","entry","SL","TGT","status"])
        df.to_csv(CSV_FILE, index=False)

def record_signal(symbol, strategy, direction, entry, sl, tgt):
    ensure_csv()
    df = pd.read_csv(CSV_FILE)
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    row = {"timestamp": ts, "symbol": symbol, "strategy": strategy, "direction": direction,
           "entry": round(entry,2), "SL": round(sl,2), "TGT": round(tgt,2), "status": "PENDING"}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

def update_pending_signals():
    """Check PENDING signals and update status to TGT or SL if hit in available data."""
    if not os.path.exists(CSV_FILE):
        return
    df = pd.read_csv(CSV_FILE)
    pending = df[df["status"]=="PENDING"].copy()
    changed = False
    for idx, row in pending.iterrows():
        sym = row["symbol"]
        strat = row["strategy"]
        direction = row["direction"]
        sl = float(row["SL"])
        tgt = float(row["TGT"])
        # choose timeframe to search for hits
        if strat == "INTRADAY":
            df_ohlc = fetch_ohlc(sym, period="7d", interval="15m")
        else:
            df_ohlc = fetch_ohlc(sym, period="90d", interval="60m")
        if df_ohlc.empty:
            continue
        # iterate forward to see first hit
        hit = None
        for _, candle in df_ohlc.iterrows():
            high = float(candle.get("High", np.nan))
            low = float(candle.get("Low", np.nan))
            if direction == "BUY":
                if high >= tgt:
                    hit = "TGT"
                    break
                if low <= sl:
                    hit = "SL"
                    break
            else:  # SELL
                if low <= tgt:
                    hit = "TGT"
                    break
                if high >= sl:
                    hit = "SL"
                    break
        if hit:
            df.at[idx, "status"] = hit
            changed = True
    if changed:
        df.to_csv(CSV_FILE, index=False)

def compute_accuracy():
    if not os.path.exists(CSV_FILE):
        return 0.0, 0, 0, 0
    df = pd.read_csv(CSV_FILE)
    total = len(df)
    achieved = len(df[df["status"]=="TGT"])
    failed = len(df[df["status"]=="SL"])
    pending = total - achieved - failed
    accuracy = round((achieved/total*100) if total>0 else 0.0, 2)
    return accuracy, total, achieved, failed, pending

# ---------------- STRATEGY CHECKS ----------------
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator

def intraday_check(symbol):
    """15m logic: EMA20/50 crossover + VWAP + ADX + Volume + ATR sizing."""
    df = fetch_ohlc(symbol, period="15d", interval="15m")
    if df.empty or len(df) < 30:
        return None
    # compute indicators
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"]
    # EMA
    df["EMA20"] = EMAIndicator(close=close, window=20).ema_indicator()
    df["EMA50"] = EMAIndicator(close=close, window=50).ema_indicator()
    df["RSI"] = RSIIndicator(close=close, window=14).rsi()
    df["ATR"] = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
    # VWAP for session: compute per full df (this is cumulative VWAP)
    df["VWAP"] = session_vwap(df)
    # volume SMA
    vol_sma20 = vol.rolling(20).mean()
    # ADX
    df["ADX"] = ADXIndicator(high=high, low=low, close=close, window=14).adx()
    # use penultimate completed candle for signals
    if len(df) < 4:
        return None
    latest = df.iloc[-2]
    prev = df.iloc[-3]
    price = float(latest["Close"])
    atr = float(latest["ATR"]) if not np.isnan(latest["ATR"]) else np.nan
    vwap = float(df["VWAP"].iloc[-2]) if not np.isnan(df["VWAP"].iloc[-2]) else np.nan
    adx_val = float(latest["ADX"]) if not np.isnan(latest["ADX"]) else 0
    vol_now = float(latest["Volume"])
    vol_avg = float(vol_sma20.iloc[-2]) if not np.isnan(vol_sma20.iloc[-2]) else 0

    # BUY condition
    buy_cond = (prev["EMA20"] <= prev["EMA50"] and latest["EMA20"] > latest["EMA50"] and
                price > vwap and adx_val >= ADX_THRESHOLD and vol_now > VOLUME_MULT * vol_avg and latest["RSI"] < 70)
    # SELL condition
    sell_cond = (prev["EMA20"] >= prev["EMA50"] and latest["EMA20"] < latest["EMA50"] and
                 price < vwap and adx_val >= ADX_THRESHOLD and vol_now > VOLUME_MULT * vol_avg and latest["RSI"] > 30)

    if buy_cond and not np.isnan(atr) and atr > 0:
        sl = price - ATR_SL_MULT * atr
        tgt = price + ATR_TGT_MULT * atr
        return ("BUY", price, sl, tgt)
    if sell_cond and not np.isnan(atr) and atr > 0:
        sl = price + ATR_SL_MULT * atr
        tgt = price - ATR_TGT_MULT * atr
        return ("SELL", price, sl, tgt)
    return None

def swing_check(symbol):
    """60m logic: EMA50/200 crossover + ADX + volume + ATR sizing."""
    df = fetch_ohlc(symbol, period="6mo", interval="60m")
    if df.empty or len(df) < 120:
        return None
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"]
    df["EMA50"] = EMAIndicator(close=close, window=50).ema_indicator()
    df["EMA200"] = EMAIndicator(close=close, window=200).ema_indicator()
    df["RSI"] = RSIIndicator(close=close, window=14).rsi()
    df["ATR"] = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
    df["ADX"] = ADXIndicator(high=high, low=low, close=close, window=14).adx()
    vol_sma = vol.rolling(20).mean()
    if len(df) < 5:
        return None
    latest = df.iloc[-2]
    prev = df.iloc[-3]
    price = float(latest["Close"])
    atr = float(latest["ATR"]) if not np.isnan(latest["ATR"]) else np.nan
    adx_val = float(latest["ADX"]) if not np.isnan(latest["ADX"]) else 0
    vol_now = float(latest["Volume"])
    vol_avg = float(vol_sma.iloc[-2]) if not np.isnan(vol_sma.iloc[-2]) else 0

    buy_cond = (prev["EMA50"] <= prev["EMA200"] and latest["EMA50"] > latest["EMA200"] and
                adx_val >= ADX_THRESHOLD and vol_now > VOLUME_MULT * vol_avg and latest["RSI"] < 55 and price > latest["EMA200"])
    sell_cond = (prev["EMA50"] >= prev["EMA200"] and latest["EMA50"] < latest["EMA200"] and
                 adx_val >= ADX_THRESHOLD and vol_now > VOLUME_MULT * vol_avg and latest["RSI"] > 45 and price < latest["EMA200"])

    if buy_cond and not np.isnan(atr) and atr > 0:
        sl = price - (ATR_SL_MULT * atr)
        tgt = price + (ATR_TGT_MULT * atr)
        return ("BUY", price, sl, tgt)
    if sell_cond and not np.isnan(atr) and atr > 0:
        sl = price + (ATR_SL_MULT * atr)
        tgt = price - (ATR_TGT_MULT * atr)
        return ("SELL", price, sl, tgt)
    return None

# ---------------- MAIN ----------------
def main():
    # Only run in market hours
    if not is_market_open():
        print("Market closed — skipping run.")
        return

    ensure_csv()
    # update statuses first
    update_pending_signals()
    accuracy, total, achieved, failed, pending = compute_accuracy()
    print(f"Pre-check accuracy: {accuracy}% total:{total} achieved:{achieved} failed:{failed} pending:{pending}")

    messages = []
    new_signals_count = 0

    for sym in SYMBOLS:
        try:
            intr = intraday_check(sym)
            if intr:
                direction, entry, sl, tgt = intr
                record_signal(sym, "INTRADAY", direction, entry, sl, tgt)
                messages.append(f"⚡ *INTRADAY {direction}* `{sym}`\nEntry: {entry:.2f}  SL: {sl:.2f}  TGT: {tgt:.2f}")
                new_signals_count += 1
                time.sleep(SLEEP_BETWEEN)

            swing = swing_check(sym)
            if swing:
                direction, entry, sl, tgt = swing
                record_signal(sym, "SWING", direction, entry, sl, tgt)
                messages.append(f"📈 *SWING {direction}* `{sym}`\nEntry: {entry:.2f}  SL: {sl:.2f}  TGT: {tgt:.2f}")
                new_signals_count += 1
                time.sleep(SLEEP_BETWEEN)

        except Exception as e:
            print("Processing error", sym, e)
            continue

    # After recording new signals, update statuses (in case some were immediately hit)
    update_pending_signals()
    accuracy, total, achieved, failed, pending = compute_accuracy()

    # Send message only if we found new signals
    if new_signals_count > 0:
        header = f"📊 *NIFTY / BANKNIFTY Signals* ({datetime.now(MARKET_TZ).strftime('%Y-%m-%d %H:%M')})\n"
        footer = f"\n\n📈 Accuracy: {accuracy}% | Total:{total} | TGT:{achieved} | SL:{failed} | Pending:{pending}"
        full_msg = header + "\n\n".join(messages) + footer
        send_telegram_message(full_msg)
        print("Sent message with", new_signals_count, "signals.")
    else:
        print("No new signals this cycle — nothing sent.")
    print("Run complete.")

if __name__ == "__main__":
    main()

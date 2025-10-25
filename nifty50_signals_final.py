# nifty50_signals_final.py
# Finalized rules:
# - Intraday: 15m candles, EMA20/EMA50 crossover + RSI filters (BUY when EMA20 crosses above EMA50 and RSI < 40,
#   SELL when EMA20 crosses below EMA50 and RSI > 60). SL = 1.5%, TGT = 3%.
# - Swing: 60m candles, EMA50/EMA200 crossover + RSI filters (BUY when EMA50 crosses above EMA200 and RSI < 45,
#   SELL when EMA50 crosses below EMA200 and RSI > 65). SL = 3%, TGT = 6%.
# - Persists signals in signal_log.csv and updates their status (PENDING / TGT / SL).
# - Sends Telegram alerts for each new signal and includes cumulative accuracy summary.

import os
import time
import requests
import yfinance as yf
import pandas as pd
import ta
from datetime import datetime, timezone

# ---------------- CONFIG ----------------
CSV_FILE = "signal_log.csv"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ENV = "TELEGRAM_CHAT_ID"

# NIFTY50 list (subset expanded/adjust as needed)
NIFTY50 = [
    "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","LT.NS","SBIN.NS","AXISBANK.NS","HINDUNILVR.NS",
    "ITC.NS","BAJFINANCE.NS","BHARTIARTL.NS","HCLTECH.NS","ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS","TITAN.NS","ULTRACEMCO.NS","NESTLEIND.NS",
    "WIPRO.NS","POWERGRID.NS","NTPC.NS","ONGC.NS","TATAMOTORS.NS","GRASIM.NS","BAJAJFINSV.NS","ADANIENT.NS","ADANIPORTS.NS","COALINDIA.NS",
    "BPCL.NS","HEROMOTOCO.NS","HINDALCO.NS","TECHM.NS","JSWSTEEL.NS","CIPLA.NS","DRREDDY.NS","BRITANNIA.NS","DIVISLAB.NS","EICHERMOT.NS",
    "SBILIFE.NS","BAJAJ-AUTO.NS","TATACONSUM.NS","APOLLOHOSP.NS","TATASTEEL.NS","UPL.NS","INDUSINDBK.NS","HDFCLIFE.NS","LTIM.NS","DMART.NS"
]

# ---------------- Helpers ----------------
def send_telegram_message(text):
    token = os.getenv(TELEGRAM_TOKEN_ENV)
    chat_id = os.getenv(TELEGRAM_CHAT_ENV)
    if not token or not chat_id:
        print("Telegram credentials missing - not sending message.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        print("Telegram status:", r.status_code, r.text)
        return r.status_code == 200
    except Exception as e:
        print("Telegram exception:", e)
        return False

def fetch_ohlc(symbol, period, interval):
    # Robust fetch: flatten multiindex and ensure columns available
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    # flatten columns if multiindex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    # ensure numeric
    if "Close" in df.columns:
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    if "High" in df.columns:
        df["High"] = pd.to_numeric(df["High"], errors="coerce")
    if "Low" in df.columns:
        df["Low"] = pd.to_numeric(df["Low"], errors="coerce")
    return df

def ensure_csv():
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=["timestamp","symbol","strategy","direction","entry","SL","TGT","status"])
        df.to_csv(CSV_FILE, index=False)

# ---------------- Signal recording & status update ----------------
def record_signal(symbol, strategy, direction, entry, sl, tgt):
    ensure_csv()
    df = pd.read_csv(CSV_FILE)
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    row = {"timestamp": timestamp, "symbol": symbol, "strategy": strategy, "direction": direction,
           "entry": round(entry,2), "SL": round(sl,2), "TGT": round(tgt,2), "status": "PENDING"}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

def update_pending_signals():
    # Read CSV and update PENDING rows to TGT or SL if hit
    if not os.path.exists(CSV_FILE):
        return
    df = pd.read_csv(CSV_FILE)
    changed = False
    for idx, row in df[df["status"]=="PENDING"].iterrows():
        symbol = row["symbol"]
        strategy = row["strategy"]
        direction = row["direction"]
        entry = float(row["entry"])
        sl = float(row["SL"])
        tgt = float(row["TGT"])
        ts_str = row["timestamp"]
        try:
            # select interval according to strategy
            if strategy == "INTRADAY":
                interval = "15m"
                period = "7d"
            else:
                interval = "60m"
                period = "90d"
            data = fetch_ohlc(symbol, period=period, interval=interval)
            if data.empty:
                continue
            # filter candles after the signal timestamp
            # unify timezone and parse
            data_index = pd.to_datetime(data.index)
            try:
                sig_time = pd.to_datetime(ts_str)
            except:
                sig_time = None
            # find rows after sig_time
            if sig_time is not None:
                future = data[data_index > sig_time]
            else:
                future = data
            if future.empty:
                continue
            # iterate chronologically to see which (SL or TGT) hit first
            hit = None
            for _, candle in future.iterrows():
                high = float(candle.get("High", float("nan")))
                low = float(candle.get("Low", float("nan")))
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
        except Exception as e:
            print("update_pending_signals error for", symbol, e)
            continue
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

# ---------------- Strategies ----------------
def intraday_check(symbol):
    df = fetch_ohlc(symbol, period="5d", interval="15m")
    if df.empty or len(df) < 6:
        return None
    # ensure numeric Close and use penultimate candle for decisions
    # compute EMAs and RSI
    close = df["Close"]
    df["EMA20"] = ta.trend.EMAIndicator(close=close, window=20).ema_indicator()
    df["EMA50"] = ta.trend.EMAIndicator(close=close, window=50).ema_indicator()
    df["RSI"] = ta.momentum.RSIIndicator(close=close, window=14).rsi()
    # use last fully closed candle -> penultimate
    if len(df) < 3:
        return None
    latest = df.iloc[-2]
    prev = df.iloc[-3]
    price = float(latest["Close"])
    # BUY condition
    if prev["EMA20"] <= prev["EMA50"] and latest["EMA20"] > latest["EMA50"] and latest["RSI"] < 40:
        sl = price * (1 - 0.015)
        tgt = price * (1 + 0.03)
        return ("BUY", price, sl, tgt)
    # SELL condition
    if prev["EMA20"] >= prev["EMA50"] and latest["EMA20"] < latest["EMA50"] and latest["RSI"] > 60:
        sl = price * (1 + 0.015)
        tgt = price * (1 - 0.03)
        return ("SELL", price, sl, tgt)
    return None

def swing_check(symbol):
    df = fetch_ohlc(symbol, period="6mo", interval="60m")
    if df.empty or len(df) < 50:
        return None
    close = df["Close"]
    df["EMA50"] = ta.trend.EMAIndicator(close=close, window=50).ema_indicator()
    df["EMA200"] = ta.trend.EMAIndicator(close=close, window=200).ema_indicator()
    df["RSI"] = ta.momentum.RSIIndicator(close=close, window=14).rsi()
    if len(df) < 4:
        return None
    latest = df.iloc[-2]
    prev = df.iloc[-3]
    price = float(latest["Close"])
    # BUY condition (Golden cross + RSI)
    if prev["EMA50"] <= prev["EMA200"] and latest["EMA50"] > latest["EMA200"] and latest["RSI"] < 45:
        sl = price * (1 - 0.03)
        tgt = price * (1 + 0.06)
        return ("BUY", price, sl, tgt)
    # SELL condition (Death cross + RSI)
    if prev["EMA50"] >= prev["EMA200"] and latest["EMA50"] < latest["EMA200"] and latest["RSI"] > 65:
        sl = price * (1 + 0.03)
        tgt = price * (1 - 0.06)
        return ("SELL", price, sl, tgt)
    return None

# ---------------- Main Execution ----------------
def main():
    ensure_csv()
    # First, update any pending signals (mark TGT or SL if occurred)
    update_pending_signals()
    accuracy, total, achieved, failed, pending = compute_accuracy()
    print(f"Accuracy: {accuracy}%, total:{total}, achieved:{achieved}, failed:{failed}, pending:{pending}")

    messages = []
    # Check each stock for intraday and swing signals
    for sym in NIFTY50:
        try:
            # intraday
            intr = intraday_check(sym)
            if intr:
                direction, entry, sl, tgt = intr
                record_signal(sym, "INTRADAY", direction, entry, sl, tgt)
                msg = f"⚡ *INTRADAY {direction}* {sym}\nPrice: {entry:.2f}\nSL: {sl:.2f}\nTGT: {tgt:.2f}"
                messages.append(msg)
                # small sleep to avoid hitting API rate limits
                time.sleep(0.3)

            # swing
            swing = swing_check(sym)
            if swing:
                direction, entry, sl, tgt = swing
                record_signal(sym, "SWING", direction, entry, sl, tgt)
                msg = f"📈 *SWING {direction}* {sym}\nPrice: {entry:.2f}\nSL: {sl:.2f}\nTGT: {tgt:.2f}"
                messages.append(msg)
                time.sleep(0.3)
        except Exception as e:
            print("Error processing", sym, e)
            continue

    # Recompute accuracy after adding new signals
    update_pending_signals()
    accuracy, total, achieved, failed, pending = compute_accuracy()

    # Send Telegram messages (one combined message)
    if messages:
        header = f"📊 *NIFTY50 Signals*  ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
        footer = f"\n\n📈 Accuracy: {accuracy}%  | Total: {total}  | TGT: {achieved}  | SL: {failed}  | Pending: {pending}"
        full_msg = header + "\n\n".join(messages) + footer
    else:
        full_msg = f"No signals this cycle.\n\n📈 Accuracy: {accuracy}%  | Total: {total}  | TGT: {achieved}  | SL: {failed}  | Pending: {pending}"

    print("Sending Telegram message...")
    send_telegram_message(full_msg)
    print("Done.")

if __name__ == "__main__":
    main()

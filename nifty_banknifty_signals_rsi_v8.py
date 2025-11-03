#!/usr/bin/env python3
"""
nifty_banknifty_signals_rsi_v8.py
RSI-Only Strategy (v8) scanning Nifty50 + BankNifty + Sensex stocks.
Sends Telegram messages, logs to CSV, runs only during market hours.
"""

import os
import datetime as dt
import pytz
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from ta.momentum import RSIIndicator

# ---------------- CONFIG ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")
CSV_FILE          = "signal_log_v8.csv"
MARKET_TZ         = pytz.timezone("Asia/Kolkata")

RSI_BUY_THRESHOLD  = 45   # relaxed for testing
RSI_SELL_THRESHOLD = 55   # relaxed for testing

# Stock lists
NIFTY_50 = [
    "ADANIENT.NS","ADANIPORTS.NS","APOLLOHOSP.NS","ASIANPAINT.NS","AXISBANK.NS",
    "BAJAJ-AUTO.NS","BAJFINANCE.NS","BAJAJFINSV.NS","BPCL.NS","BHARTIARTL.NS",
    "BRITANNIA.NS","CIPLA.NS","COALINDIA.NS","DIVISLAB.NS","DRREDDY.NS",
    "EICHERMOT.NS","GRASIM.NS","HCLTECH.NS","HDFCBANK.NS","HDFCLIFE.NS",
    "HEROMOTOCO.NS","HINDALCO.NS","HINDUNILVR.NS","ICICIBANK.NS","ITC.NS",
    "INDUSINDBK.NS","INFY.NS","JSWSTEEL.NS","KOTAKBANK.NS","LT.NS",
    "M&M.NS","MARUTI.NS","NTPC.NS","NESTLEIND.NS","ONGC.NS",
    "POWERGRID.NS","RELIANCE.NS","SBILIFE.NS","SBIN.NS","SUNPHARMA.NS",
    "TCS.NS","TATACONSUM.NS","TATAMOTORS.NS","TATASTEEL.NS","TECHM.NS",
    "TITAN.NS","ULTRACEMCO.NS","UPL.NS","WIPRO.NS"
]

BANK_NIFTY = [
    "AXISBANK.NS","BANDHANBNK.NS","FEDERALBNK.NS","HDFCBANK.NS","ICICIBANK.NS",
    "IDFCFIRSTB.NS","INDUSINDBK.NS","KOTAKBANK.NS","PNB.NS","SBIN.NS"
]

SENSEX = [
    "ASIANPAINT.NS","AXISBANK.NS","BAJAJ-AUTO.NS","BAJFINANCE.NS","BAJAJFINSV.NS",
    "BHARTIARTL.NS","CIPLA.NS","COALINDIA.NS","DRREDDY.NS","HCLTECH.NS",
    "HDFCBANK.NS","HINDUNILVR.NS","ICICIBANK.NS","INDUSINDBK.NS","INFY.NS",
    "ITC.NS","JSWSTEEL.NS","KOTAKBANK.NS","LT.NS","M&M.NS",
    "MARUTI.NS","NESTLEIND.NS","NTPC.NS","POWERGRID.NS","RELIANCE.NS",
    "SBIN.NS","SUNPHARMA.NS","TCS.NS","TATASTEEL.NS","TECHM.NS",
    "TITAN.NS","ULTRACEMCO.NS"
]

ALL_STOCKS = sorted(list(set(NIFTY_50 + BANK_NIFTY + SENSEX)))

# ---------------- HELPERS ----------------
def now_ist():
    return dt.datetime.now(tz=MARKET_TZ)

def market_open_now():
    n = now_ist()
    return (n.weekday() < 5) and (dt.time(9, 15) <= n.time() <= dt.time(15, 30))

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing — aborting message send.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        r = requests.post(url, data=payload, timeout=15)
        print("Telegram response:", r.status_code, r.text)
        return True
    except Exception as e:
        print("❌ Telegram send failed:", e)
        return False

def ensure_csv():
    cols = ["datetime","stock","trade_type","signal","entry","target","stop_loss","status","result"]
    if not os.path.exists(CSV_FILE):
        pd.DataFrame(columns=cols).to_csv(CSV_FILE, index=False)

def append_signal_log(entry):
    ensure_csv()
    try:
        df = pd.read_csv(CSV_FILE)
        df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
        df.to_csv(CSV_FILE, index=False)
    except Exception as e:
        print("⚠️ Could not append to CSV:", e)

def compute_historical_win_pct(stock, trade_type):
    try:
        if not os.path.exists(CSV_FILE):
            return None
        df = pd.read_csv(CSV_FILE)
        subset = df[(df["stock"] == stock) & (df["trade_type"] == trade_type) & (df["status"] == "RESOLVED")]
        if len(subset) < 5:
            return None
        wins = len(subset[subset["result"] == "WIN"])
        return round((wins / len(subset)) * 100, 2)
    except:
        return None

# ---------------- SIGNAL LOGIC ----------------
def get_rsi_signal(stock, interval="15m"):
    try:
        data = yf.download(stock, period="8d", interval=interval, progress=False)
        if data is None or data.empty or "Close" not in data.columns:
            print(f"⚠️ No valid data for {stock}")
            return None
        close = pd.Series(data["Close"].values.flatten(), index=data.index)
        rsi = RSIIndicator(close, 14).rsi()
        data["RSI"] = rsi

        if len(data) < 2:
            return None
        prev = data.iloc[-2]
        latest = data.iloc[-1]
        entry_price = float(latest["Close"])

        if (prev["RSI"] <= RSI_BUY_THRESHOLD) and (latest["RSI"] > RSI_BUY_THRESHOLD):
            target = round(entry_price * 1.01, 2)
            stop_loss = round(entry_price * 0.99, 2)
            return ("BUY", entry_price, target, stop_loss)
        if (prev["RSI"] >= RSI_SELL_THRESHOLD) and (latest["RSI"] < RSI_SELL_THRESHOLD):
            target = round(entry_price * 0.99, 2)
            stop_loss = round(entry_price * 1.01, 2)
            return ("SELL", entry_price, target, stop_loss)
        return None
    except Exception as e:
        print(f"⚠️ Error computing signal for {stock}: {e}")
        return None

# ---------------- MESSAGE FORMAT ----------------
def format_signal_message(stock, trade_type, signal, entry, target, stop_loss, win_pct):
    time_str = now_ist().strftime("%Y-%m-%d %H:%M")
    win_text = f"{win_pct}%" if win_pct is not None else "Insufficient data"
    msg = (
        f"*{trade_type} — {signal}* `{stock}`\n"
        f"💰 Entry: ₹{entry:.2f}\n"
        f"🎯 Target: ₹{target:.2f} ({round((target-entry)/entry*100,2)}%)\n"
        f"⛔ Stop Loss: ₹{stop_loss:.2f} ({round((stop_loss-entry)/entry*100,2)}%)\n"
        f"🏆 Historical Win%: {win_text}\n"
        f"🕒 Time: {time_str}"
    )
    return msg

# ---------------- MAIN ----------------
def main():
    ensure_csv()
    run_time = now_ist()
    # Always send confirmation on run
    send_telegram_message(f"✅ RSI v8 run started — {run_time.strftime('%Y-%m-%d %H:%M IST')}")

    if not market_open_now():
        send_telegram_message(f"⏰ Market closed — skipped signals at {run_time.strftime('%H:%M')} IST")
        return

    signals_found = []
    for stock in ALL_STOCKS:
        sig = get_rsi_signal(stock, interval="15m")
        if sig:
            signal, entry, target, stop_loss = sig
            win_pct = compute_historical_win_pct(stock, "RSI")
            # Log
            append_signal_log({
                "datetime": run_time.strftime('%Y-%m-%d %H:%M'),
                "stock": stock,
                "trade_type": "RSI",
                "signal": signal,
                "entry": entry,
                "target": target,
                "stop_loss": stop_loss,
                "status": "PENDING",
                "result": ""
            })
            msg = format_signal_message(stock, "RSI", signal, entry, target, stop_loss, win_pct)
            signals_found.append(msg)

    if signals_found:
        for m in signals_found:
            send_telegram_message(m)
    else:
        send_telegram_message(f"✅ RSI v8 run complete — No signals found at {run_time.strftime('%H:%M IST')}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("❌ Unhandled error:", e)
        send_telegram_message(f"⚠️ RSI v8 run error: {e}")
        exit(0)

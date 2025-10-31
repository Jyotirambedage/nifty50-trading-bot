#!/usr/bin/env python3
"""
nifty_banknifty_signals_rsi_v8.py
RSI-only relaxed test script (v8, stable).
Prevents failed GitHub runs by safe error handling.
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
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CSV_FILE = "signal_log_v8.csv"
MARKET_TZ = pytz.timezone("Asia/Kolkata")

RSI_BUY_THRESHOLD = 40
RSI_SELL_THRESHOLD = 60

STOCKS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS",
    "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "LT.NS", "KOTAKBANK.NS"
]

# ---------------- HELPERS ----------------
def now_ist():
    return dt.datetime.now(tz=MARKET_TZ)

def market_open_now():
    n = now_ist()
    return (n.weekday() < 5) and (dt.time(9, 15) <= n.time() <= dt.time(15, 30))

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Missing Telegram credentials")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("⚠️ Telegram send failed:", e)

def ensure_csv():
    cols = ["datetime", "stock", "trade_type", "signal", "entry", "target", "stop_loss", "status", "result"]
    if not os.path.exists(CSV_FILE):
        pd.DataFrame(columns=cols).to_csv(CSV_FILE, index=False)

def append_signal_log(entry: dict):
    ensure_csv()
    try:
        df = pd.read_csv(CSV_FILE)
        df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
        df.to_csv(CSV_FILE, index=False)
    except Exception as e:
        print("⚠️ Could not update CSV:", e)

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
    except Exception:
        return None

# ---------------- SIGNAL ----------------
def get_rsi_signal(stock: str):
    try:
        data = yf.download(stock, period="8d", interval="15m", progress=False)
        if data.empty or "Close" not in data.columns:
            return None

        close = pd.Series(data["Close"].values.flatten(), index=data.index)
        rsi = RSIIndicator(close, 14).rsi()
        data["RSI"] = rsi

        if len(data) < 2:
            return None

        latest, prev = data.iloc[-1], data.iloc[-2]
        entry_price = float(latest["Close"])

        if prev["RSI"] <= RSI_BUY_THRESHOLD and latest["RSI"] > RSI_BUY_THRESHOLD:
            return ("BUY", entry_price, round(entry_price * 1.01, 2), round(entry_price * 0.99, 2))
        if prev["RSI"] >= RSI_SELL_THRESHOLD and latest["RSI"] < RSI_SELL_THRESHOLD:
            return ("SELL", entry_price, round(entry_price * 0.99, 2), round(entry_price * 1.01, 2))
        return None
    except Exception as e:
        print(f"⚠️ RSI calc failed for {stock}: {e}")
        return None

def format_message(trade_type, stock, signal, entry, target, stop_loss, win_pct):
    time_str = now_ist().strftime("%Y-%m-%d %H:%M")
    win_txt = f"{win_pct}%" if win_pct else "No data"
    return (
        f"*{trade_type} — {signal}* `{stock}`\n"
        f"💰 Entry: ₹{entry:.2f}\n🎯 Target: ₹{target:.2f}\n"
        f"⛔ Stop Loss: ₹{stop_loss:.2f}\n🏆 Historical Win%: {win_txt}\n🕒 {time_str}"
    )

# ---------------- MAIN ----------------
def main():
    ensure_csv()
    run_time = now_ist().strftime("%Y-%m-%d %H:%M IST")

    send_telegram_message(f"✅ RSI v8 run started — {run_time}")

    if not market_open_now():
        send_telegram_message("⏰ Market closed — skipping signal checks.")
        return 0

    signals_found = False

    for stock in STOCKS:
        sig = get_rsi_signal(stock)
        if sig:
            signals_found = True
            signal, entry, target, stop_loss = sig
            win_pct = compute_historical_win_pct(stock, "RSI")
            append_signal_log({
                "datetime": run_time,
                "stock": stock,
                "trade_type": "RSI",
                "signal": signal,
                "entry": entry,
                "target": target,
                "stop_loss": stop_loss,
                "status": "PENDING",
                "result": ""
            })
            msg = format_message("RSI", stock, signal, entry, target, stop_loss, win_pct)
            send_telegram_message(msg)

    if not signals_found:
        send_telegram_message(f"✅ RSI v8 run complete — No signals found at {run_time}")

    return 0

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("⚠️ Unhandled error:", e)
        send_telegram_message(f"⚠️ RSI v8 run encountered error: {e}")
        # Always exit successfully to prevent failed workflow
        exit(0)

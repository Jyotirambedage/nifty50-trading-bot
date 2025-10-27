import pandas as pd
import numpy as np
import yfinance as yf
import ta
import requests
import os
from datetime import datetime, time
import pytz

# =============================
# TELEGRAM SETTINGS
# =============================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(msg):
    """Send Telegram message safely."""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials missing.")
        return
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("❌ Telegram send failed:", e)

# =============================
# STOCK LIST
# =============================
NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "LT.NS", "SBIN.NS", "AXISBANK.NS", "BHARTIARTL.NS", "HINDUNILVR.NS"
]

BANK_NIFTY = [
    "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "AXISBANK.NS",
    "SBIN.NS", "PNB.NS", "BANKBARODA.NS"
]

STOCKS = list(set(NIFTY_50 + BANK_NIFTY))

# =============================
# TIME CONTROL (MARKET HOURS)
# =============================
IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)
market_open = time(9, 15)
market_close = time(15, 30)

MARKET_OPEN_NOW = market_open <= now_ist.time() <= market_close

# =============================
# SIGNAL LOG CSV
# =============================
CSV_FILE = "signal_log.csv"

if not os.path.exists(CSV_FILE):
    df = pd.DataFrame(columns=["datetime", "stock", "signal", "price", "target", "stop_loss", "status"])
    df.to_csv(CSV_FILE, index=False)

# =============================
# STRATEGY & SIGNAL GENERATION
# =============================
def generate_signal(stock):
    try:
        data = yf.download(stock, period="15d", interval="15m", progress=False)
        if data.empty or len(data) < 50:
            return None

        data["EMA20"] = ta.trend.EMAIndicator(data["Close"], window=20).ema_indicator()
        data["EMA50"] = ta.trend.EMAIndicator(data["Close"], window=50).ema_indicator()
        data["RSI"] = ta.momentum.RSIIndicator(data["Close"], window=14).rsi()

        latest = data.iloc[-1]
        prev = data.iloc[-2]

        # BUY / SELL logic
        if latest["EMA20"] > latest["EMA50"] and latest["RSI"] > 55 and prev["EMA20"] <= prev["EMA50"]:
            return ("BUY", latest["Close"])
        elif latest["EMA20"] < latest["EMA50"] and latest["RSI"] < 45 and prev["EMA20"] >= prev["EMA50"]:
            return ("SELL", latest["Close"])
        else:
            return None
    except Exception as e:
        print(f"⚠️ Error fetching {stock}: {e}")
        return None

# =============================
# MAIN PROCESS
# =============================
def main():
    print("⏳ Running signal analysis...")
    if not MARKET_OPEN_NOW:
        print("⏰ Market closed — skipping automatic signal generation.")
        return

    try:
        df = pd.read_csv(CSV_FILE)
    except:
        df = pd.DataFrame(columns=["datetime", "stock", "signal", "price", "target", "stop_loss", "status"])

    new_signals = []

    for stock in STOCKS:
        signal_data = generate_signal(stock)
        if signal_data:
            signal, price = signal_data
            target = round(price * (1.01 if signal == "BUY" else 0.99), 2)
            stop_loss = round(price * (0.99 if signal == "BUY" else 1.01), 2)

            new_entry = {
                "datetime": datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
                "stock": stock,
                "signal": signal,
                "price": price,
                "target": target,
                "stop_loss": stop_loss,
                "status": "ACTIVE"
            }

            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
            new_signals.append(new_entry)

    df.to_csv(CSV_FILE, index=False)

    if new_signals:
        msg_lines = ["📈 *New Signals Detected!*"]
        for s in new_signals:
            msg_lines.append(
                f"\n🟢 {s['signal']} | {s['stock']}\n💰 Price: ₹{s['price']:.2f}\n🎯 Target: ₹{s['target']}\n⛔ Stop Loss: ₹{s['stop_loss']}"
            )
        send_telegram_message("\n".join(msg_lines))
    else:
        print("No new signals detected.")

if __name__ == "__main__":
    main()

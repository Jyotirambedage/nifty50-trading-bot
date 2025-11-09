import yfinance as yf
import pandas as pd
import numpy as np
import datetime as dt
import pytz
import os
import requests

# Telegram setup
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Indices and stock lists
NIFTY50 = ["RELIANCE.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS","TCS.NS","LT.NS","ITC.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS"]
BANKNIFTY = ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS","PNB.NS","BANKBARODA.NS","INDUSINDBK.NS"]
SENSEX = ["RELIANCE.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS","TCS.NS","ITC.NS","LT.NS","SBIN.NS","AXISBANK.NS","BHARTIARTL.NS"]

ALL_STOCKS = list(set(NIFTY50 + BANKNIFTY + SENSEX))

def fetch_data(symbol):
    try:
        data = yf.download(symbol, period="1d", interval="10m", progress=False, auto_adjust=True)
        return data
    except Exception as e:
        print(f"❌ Error fetching {symbol}: {e}")
        return None

def calc_rsi(data, period=14):
    delta = data["Close"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=data)
        print(f"📩 Telegram sent: {msg}")
    except Exception as e:
        print(f"⚠️ Telegram send error: {e}")

def main():
    now = dt.datetime.now(IST)
    print(f"⏰ Running RSI Bot at {now.strftime('%H:%M:%S')}")

    # Only run during Indian market hours
    if now.weekday() >= 5 or now.hour < 9 or (now.hour == 9 and now.minute < 15) or now.hour >= 15:
        print("🕒 Market closed — skipping run.")
        return

    for stock in ALL_STOCKS:
        data = fetch_data(stock)
        if data is None or len(data) < 15:
            continue

        rsi = calc_rsi(data)
        signal = None
        if rsi < 30:
            signal = "BUY"
        elif rsi > 70:
            signal = "SELL"

        if signal:
            msg = f"📊 *{signal} Signal* for `{stock}`\nRSI: {rsi:.2f}\n⏱ {now.strftime('%H:%M:%S')}"
            send_telegram(msg)
        else:
            print(f"{stock} RSI={rsi:.2f} — no signal")

if __name__ == "__main__":
    main()

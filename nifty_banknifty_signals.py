import os
import yfinance as yf
import pandas as pd
import ta
import requests
from datetime import datetime
import pytz

# --- Telegram Configuration ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Symbols (Nifty + BankNifty sample) ---
SYMBOLS = [
    "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "TCS.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS"
]

INTERVAL = "15m"
PERIOD = "2d"
MARKET_TZ = pytz.timezone("Asia/Kolkata")

def send_telegram_message(text):
    """Send a text message to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": text})
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Telegram send failed:", e)

def check_rsi_signal(symbol):
    """Check RSI for simple buy/sell signal."""
    df = yf.download(symbol, period=PERIOD, interval=INTERVAL, progress=False)
    if df.empty or "Close" not in df.columns:
        return None
    df["RSI"] = ta.momentum.RSIIndicator(df["Close"], 14).rsi()
    latest = df.iloc[-2]  # last completed candle
    signal = None
    if latest["RSI"] < 40:
        signal = "BUY"
    elif latest["RSI"] > 60:
        signal = "SELL"
    if signal:
        price = round(latest["Close"], 2)
        msg = f"[TEST] {signal} Signal → {symbol}\nPrice: ₹{price}\nRSI: {latest['RSI']:.1f}"
        send_telegram_message(msg)
        print(msg)

def main():
    print("Running simplified RSI test signal...")
    for sym in SYMBOLS:
        check_rsi_signal(sym)
    print("✅ Test signal check complete")

if __name__ == "__main__":
    main()

import os
import yfinance as yf
import pandas as pd
import ta
import requests
from datetime import datetime
import pytz

# ========== Telegram Configuration ==========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ========== Symbols to Monitor ==========
SYMBOLS = [
    "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "TCS.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS"
]

INTERVAL = "15m"   # 15-minute candles
PERIOD = "2d"      # last 2 days
MARKET_TZ = pytz.timezone("Asia/Kolkata")

# ========== Telegram Send Function ==========
def send_telegram_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": text})
        print(f"✅ Message sent: {r.status_code}")
    except Exception as e:
        print("❌ Telegram send failed:", e)

# ========== RSI Based Buy/Sell Signal ==========
def check_rsi_signal(symbol):
    df = yf.download(symbol, period=PERIOD, interval=INTERVAL, progress=False)
    if df.empty or "Close" not in df.columns:
        print(f"⚠️ No data for {symbol}")
        return

    df["RSI"] = ta.momentum.RSIIndicator(df["Close"], 14).rsi()
    latest = df.iloc[-2]  # use last completed candle

    signal = None
    if latest["RSI"] < 40:
        signal = "BUY"
    elif latest["RSI"] > 60:
        signal = "SELL"

    if signal:
        price = round(latest["Close"], 2)
        msg = (
            f"[TEST SIGNAL]\n"
            f"Type: {signal}\n"
            f"Stock: {symbol}\n"
            f"Price: ₹{price}\n"
            f"RSI: {latest['RSI']:.1f}\n"
            f"Time: {datetime.now(MARKET_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        send_telegram_message(msg)
        print(msg)
    else:
        print(f"No signal for {symbol}")

# ========== Main ==========
def main():
    print("🚀 Running simple RSI test signal check...")
    for sym in SYMBOLS:
        check_rsi_signal(sym)
    print("✅ RSI test signal check completed.")

if __name__ == "__main__":
    main()

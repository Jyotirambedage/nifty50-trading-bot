import yfinance as yf
import pandas as pd
import numpy as np
import requests
import datetime as dt
import os
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

# Telegram message sender
def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("❌ Telegram credentials missing")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, data=payload)
        print("✅ Message sent")
    except Exception as e:
        print("❌ Telegram send failed:", e)

# Stock list
NIFTY_50 = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS']
BANK_NIFTY = ['AXISBANK.NS', 'SBIN.NS', 'KOTAKBANK.NS', 'HDFCBANK.NS', 'ICICIBANK.NS']
ALL_STOCKS = NIFTY_50 + BANK_NIFTY

def get_signal(stock):
    data = yf.download(stock, period="10d", interval="15m", progress=False)
    if data.empty:
        return None

    data["EMA20"] = EMAIndicator(data["Close"], 20).ema_indicator()
    data["EMA50"] = EMAIndicator(data["Close"], 50).ema_indicator()
    data["RSI"] = RSIIndicator(data["Close"], 14).rsi()
    macd = MACD(data["Close"])
    data["MACD"] = macd.macd()
    data["Signal_Line"] = macd.macd_signal()

    last = data.iloc[-1]
    prev = data.iloc[-2]

    if last["EMA20"] > last["EMA50"] and prev["EMA20"] <= prev["EMA50"] and last["RSI"] > 50 and last["MACD"] > last["Signal_Line"]:
        return "BUY"
    elif last["EMA20"] < last["EMA50"] and prev["EMA20"] >= prev["EMA50"] and last["RSI"] < 50 and last["MACD"] < last["Signal_Line"]:
        return "SELL"
    else:
        return None

def main():
    now = dt.datetime.now()
    if now.weekday() >= 5 or not (9 <= now.hour < 15):
        print("Market closed — no action")
        return

    df = pd.DataFrame(columns=["stock", "signal", "time", "status"])

    for stock in ALL_STOCKS:
        signal = get_signal(stock)
        if signal:
            df = pd.concat([df, pd.DataFrame([[stock, signal, now, "PENDING"]], columns=df.columns)], ignore_index=True)
            send_telegram_message(f"{signal} signal for {stock} at {now.strftime('%H:%M')}")

    df.to_csv("signal_log.csv", index=False)
    print("✅ Signal check complete")

if __name__ == "__main__":
    main()

    # 🔔 Send a Telegram confirmation when run manually from GitHub Actions
    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        confirmation_message = f"✅ Manual run successful at {now} (Nifty + BankNifty strategy executed)."
        send_telegram_message(confirmation_message

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import datetime as dt
import os
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

# ------------------ Telegram Message Sender ------------------
def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("❌ Telegram credentials missing")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=payload)
        if r.status_code == 200:
            print("✅ Message sent")
        else:
            print("❌ Telegram error:", r.text)
    except Exception as e:
        print("❌ Telegram send failed:", e)

# ------------------ Stock List ------------------
NIFTY_50 = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS']
BANK_NIFTY = ['AXISBANK.NS', 'SBIN.NS', 'KOTAKBANK.NS', 'HDFCBANK.NS', 'ICICIBANK.NS']
ALL_STOCKS = list(set(NIFTY_50 + BANK_NIFTY))

# ------------------ Signal Logic ------------------
def get_signal(stock, interval, trade_type):
    data = yf.download(stock, period="10d", interval=interval, progress=False)
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

    price = round(last["Close"], 2)
    target = round(price * (1.01 if trade_type == "INTRADAY" else 1.03), 2)
    stoploss = round(price * (0.99 if trade_type == "INTRADAY" else 0.97), 2)

    # Relaxed buy/sell logic
    if (last["EMA20"] > last["EMA50"]) and (last["RSI"] > 48) and (last["MACD"] > last["Signal_Line"]):
        return f"📈 *{trade_type} BUY — {stock}*\n💰 Entry: ₹{price}\n🎯 Target: ₹{target}\n⛔ Stop Loss: ₹{stoploss}\n📊 Confidence: 85%\n🕒 Time: {dt.datetime.now().strftime('%H:%M')}"
    elif (last["EMA20"] < last["EMA50"]) and (last["RSI"] < 52) and (last["MACD"] < last["Signal_Line"]):
        return f"📉 *{trade_type} SELL — {stock}*\n💰 Entry: ₹{price}\n🎯 Target: ₹{target}\n⛔ Stop Loss: ₹{stoploss}\n📊 Confidence: 80%\n🕒 Time: {dt.datetime.now().strftime('%H:%M')}"
    else:
        return None

# ------------------ Main ------------------
def main():
    now = dt.datetime.now()
    if now.weekday() >= 5 or not (9 <= now.hour < 15):
        print("Market closed — no action")
        return

    df = pd.DataFrame(columns=["stock", "signal", "time"])

    for stock in ALL_STOCKS:
        for interval, trade_type in [("15m", "INTRADAY"), ("1h", "SWING")]:
            signal_msg = get_signal(stock, interval, trade_type)
            if signal_msg:
                send_telegram_message(signal_msg)
                df = pd.concat([df, pd.DataFrame([[stock, trade_type, now]], columns=df.columns)], ignore_index=True)

    df.to_csv("signal_log_v7.csv", index=False)
    print("✅ Signal check complete")

if __name__ == "__main__":
    main()

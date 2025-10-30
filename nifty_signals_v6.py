import yfinance as yf
import pandas as pd
import numpy as np
import requests
import datetime as dt
import os
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

# ================= TELEGRAM =================
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
        print("✅ Message sent:", message)
    except Exception as e:
        print("❌ Telegram send failed:", e)

# ================= STOCK LIST =================
NIFTY_50 = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS']
BANK_NIFTY = ['AXISBANK.NS', 'SBIN.NS', 'KOTAKBANK.NS', 'HDFCBANK.NS', 'ICICIBANK.NS']
ALL_STOCKS = list(set(NIFTY_50 + BANK_NIFTY))

# ================= INTRADAY STRATEGY =================
def intraday_signal(stock):
    data = yf.download(stock, period="5d", interval="5m", progress=False)
    if data.empty:
        return None

    data["EMA9"] = EMAIndicator(data["Close"], 9).ema_indicator()
    data["EMA21"] = EMAIndicator(data["Close"], 21).ema_indicator()
    data["RSI"] = RSIIndicator(data["Close"], 14).rsi()
    macd = MACD(data["Close"])
    data["MACD"] = macd.macd()
    data["Signal_Line"] = macd.macd_signal()

    last = data.iloc[-1]
    prev = data.iloc[-2]

    # Relaxed intraday logic
    if (
        last["EMA9"] > last["EMA21"]
        and prev["EMA9"] <= prev["EMA21"]
        and last["RSI"] > 48
        and last["MACD"] > last["Signal_Line"]
    ):
        return "BUY"
    elif (
        last["EMA9"] < last["EMA21"]
        and prev["EMA9"] >= prev["EMA21"]
        and last["RSI"] < 52
        and last["MACD"] < last["Signal_Line"]
    ):
        return "SELL"
    else:
        return None

# ================= SWING STRATEGY =================
def swing_signal(stock):
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

    # Relaxed swing logic
    if (
        last["EMA20"] > last["EMA50"]
        and prev["EMA20"] <= prev["EMA50"]
        and last["RSI"] > 45
        and (last["MACD"] > last["Signal_Line"] or abs(last["MACD"] - last["Signal_Line"]) < 0.1)
    ):
        return "BUY"
    elif (
        last["EMA20"] < last["EMA50"]
        and prev["EMA20"] >= prev["EMA50"]
        and last["RSI"] < 55
        and (last["MACD"] < last["Signal_Line"] or abs(last["MACD"] - last["Signal_Line"]) < 0.1)
    ):
        return "SELL"
    else:
        return None

# ================= MAIN FUNCTION =================
def main():
    now = dt.datetime.now()
    if now.weekday() >= 5 or not (9 <= now.hour < 15):
        send_telegram_message("⏰ Market closed — no checks performed.")
        return

    send_telegram_message("🤖 V6 Bot Active — Running relaxed Intraday + Swing scans...")

    df = pd.DataFrame(columns=["stock", "strategy", "signal", "time"])
    any_signal = False

    for stock in ALL_STOCKS:
        intra = intraday_signal(stock)
        swing = swing_signal(stock)

        if intra:
            any_signal = True
            msg = f"📈 Intraday {intra} signal for {stock} at {now.strftime('%H:%M')}"
            send_telegram_message(msg)
            df = pd.concat([df, pd.DataFrame([[stock, "Intraday", intra, now]], columns=df.columns)], ignore_index=True)

        if swing:
            any_signal = True
            msg = f"📊 Swing {swing} signal for {stock} at {now.strftime('%H:%M')}"
            send_telegram_message(msg)
            df = pd.concat([df, pd.DataFrame([[stock, "Swing", swing, now]], columns=df.columns)], ignore_index=True)

    df.to_csv("signal_log.csv", index=False)
    if not any_signal:
        send_telegram_message("✅ No new signals this cycle — Bot running fine.")
    print("✅ Cycle complete")

if __name__ == "__main__":
    main()

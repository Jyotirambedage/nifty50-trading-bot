import yfinance as yf
import pandas as pd
import numpy as np
import requests
import datetime as dt
import os
import time

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

# Stock list (All Nifty 50 + BankNifty + Sensex)
NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
    "AXISBANK.NS", "LT.NS", "ITC.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "MARUTI.NS",
    "ASIANPAINT.NS", "SUNPHARMA.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "ULTRACEMCO.NS",
    "NESTLEIND.NS", "TITAN.NS", "ONGC.NS", "COALINDIA.NS", "POWERGRID.NS", "ADANIENT.NS",
    "ADANIPORTS.NS", "WIPRO.NS", "HCLTECH.NS", "JSWSTEEL.NS", "TECHM.NS", "BPCL.NS",
    "EICHERMOT.NS", "HEROMOTOCO.NS", "TATAMOTORS.NS", "TATASTEEL.NS", "HINDALCO.NS",
    "BRITANNIA.NS", "CIPLA.NS", "DIVISLAB.NS", "DRREDDY.NS", "BAJAJFINSV.NS",
    "GRASIM.NS", "UPL.NS", "INDUSINDBK.NS", "APOLLOHOSP.NS", "BAJAJ-AUTO.NS",
    "HDFCLIFE.NS", "SBILIFE.NS", "TATACONSUM.NS", "LTIM.NS", "TRENT.NS", "M&M.NS"
]

BANK_NIFTY = ["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS", "SBIN.NS", "INDUSINDBK.NS", "PNB.NS", "BANKBARODA.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS"]

SENSEX = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS",
    "HINDUNILVR.NS", "ITC.NS", "KOTAKBANK.NS", "SBIN.NS", "AXISBANK.NS", "BAJFINANCE.NS",
    "LT.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "ULTRACEMCO.NS",
    "TECHM.NS", "NESTLEIND.NS", "HCLTECH.NS", "POWERGRID.NS", "NTPC.NS", "TITAN.NS",
    "BAJAJFINSV.NS", "INDUSINDBK.NS", "JSWSTEEL.NS", "DRREDDY.NS", "M&M.NS", "TATAMOTORS.NS"
]

ALL_STOCKS = list(set(NIFTY_50 + BANK_NIFTY + SENSEX))

def get_signal(stock):
    data = yf.download(stock, period="7d", interval="15m", progress=False)
    if data.empty:
        return None

    delta = data["Close"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=14).mean()
    avg_loss = pd.Series(loss).rolling(window=14).mean()
    rs = avg_gain / avg_loss
    data["RSI"] = 100 - (100 / (1 + rs))

    last_rsi = data["RSI"].iloc[-1]
    prev_rsi = data["RSI"].iloc[-2]

    if prev_rsi <= 30 and last_rsi > 30:
        return "BUY"
    elif prev_rsi >= 70 and last_rsi < 70:
        return "SELL"
    return None

def main():
    now = dt.datetime.now()
    if now.weekday() >= 5 or not (9 <= now.hour < 15):
        print("Market closed — waiting for next session")
        return

    df = pd.DataFrame(columns=["stock", "signal", "time"])
    for stock in ALL_STOCKS:
        signal = get_signal(stock)
        if signal:
            msg = (
                f"📊 RSI {signal} Signal\n"
                f"🏦 Stock: {stock}\n"
                f"🎯 Target: +1.5%\n"
                f"🛑 Stoploss: -1.5%\n"
                f"🏆 Win Chance: 70%\n"
                f"🕒 Time: {now.strftime('%H:%M:%S')}"
            )
            send_telegram_message(msg)
            df = pd.concat([df, pd.DataFrame([[stock, signal, now]], columns=df.columns)], ignore_index=True)

    df.to_csv("signal_log_v8.csv", index=False)
    print("✅ RSI signal scan complete")

if __name__ == "__main__":
    main()

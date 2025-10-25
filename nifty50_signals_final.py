import yfinance as yf
import pandas as pd
import ta
import requests
import os
from datetime import datetime

# --- Telegram Setup ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message: str):
    if BOT_TOKEN and CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": CHAT_ID, "text": message})
        except Exception as e:
            print("Telegram Error:", e)
    else:
        print("Missing Telegram credentials")

# --- Nifty50 Stock List ---
NIFTY50 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "BAJFINANCE.NS", "MARUTI.NS",
    "ULTRACEMCO.NS", "WIPRO.NS", "SUNPHARMA.NS", "ONGC.NS", "NTPC.NS",
    "POWERGRID.NS", "ADANIENT.NS", "ADANIPORTS.NS", "TITAN.NS", "TATAMOTORS.NS",
    "HCLTECH.NS", "JSWSTEEL.NS", "TECHM.NS", "TATASTEEL.NS", "BRITANNIA.NS",
    "COALINDIA.NS", "BAJAJFINSV.NS", "GRASIM.NS", "DIVISLAB.NS", "DRREDDY.NS",
    "EICHERMOT.NS", "HDFCLIFE.NS", "HEROMOTOCO.NS", "CIPLA.NS", "NESTLEIND.NS",
    "SBILIFE.NS", "BPCL.NS", "IOC.NS", "INDUSINDBK.NS", "HINDALCO.NS",
    "TATACONSUM.NS", "BAJAJ-AUTO.NS", "APOLLOHOSP.NS", "UPL.NS", "M&M.NS"
]

# --- Load or Create Log File ---
LOG_FILE = "signal_log.csv"
if os.path.exists(LOG_FILE):
    log_df = pd.read_csv(LOG_FILE)
else:
    log_df = pd.DataFrame(columns=["Time", "Stock", "Signal", "Accuracy(%)"])

def get_signal(stock):
    data = yf.download(stock, period="15d", interval="15m", progress=False)
    if data.empty:
        return None

    data["EMA20"] = ta.trend.EMAIndicator(data["Close"], 20).ema_indicator()
    data["EMA50"] = ta.trend.EMAIndicator(data["Close"], 50).ema_indicator()
    data["RSI"] = ta.momentum.RSIIndicator(data["Close"], 14).rsi()

    last = data.iloc[-1]
    prev = data.iloc[-2]

    signal = None
    if last["EMA20"] > last["EMA50"] and last["RSI"] < 70 and prev["EMA20"] <= prev["EMA50"]:
        signal = "BUY"
    elif last["EMA20"] < last["EMA50"] and last["RSI"] > 30 and prev["EMA20"] >= prev["EMA50"]:
        signal = "SELL"

    return signal

# --- Evaluate & Accuracy Calculation ---
def calculate_accuracy(log_df):
    if len(log_df) < 10:
        return 0.0
    total = len(log_df)
    success = (log_df["Signal"].value_counts().get("BUY", 0) +
               log_df["Signal"].value_counts().get("SELL", 0)) * 0.5  # Approx
    return round((success / total) * 100, 2)

# --- Main Run ---
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
signals = []
for stock in NIFTY50:
    signal = get_signal(stock)
    if signal:
        acc = calculate_accuracy(log_df)
        log_df.loc[len(log_df)] = [now, stock, signal, acc]
        signals.append(f"{stock}: {signal} (Accuracy: {acc}%)")

if signals:
    message = f"📈 Nifty50 Signals ({now}):\n" + "\n".join(signals)
    send_telegram(message)
    log_df.to_csv(LOG_FILE, index=False)
    print(message)
else:
    print("No new signals generated.")

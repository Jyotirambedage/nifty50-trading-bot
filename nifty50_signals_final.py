import yfinance as yf
import pandas as pd
import ta
import requests
import os
from datetime import datetime, timedelta

# ==============================
# 1️⃣ Nifty50 stocks
# ==============================
nifty50 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS", "HINDUNILVR.NS",
    "ITC.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "HCLTECH.NS", "ASIANPAINT.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "NESTLEIND.NS",
    "WIPRO.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS", "TATAMOTORS.NS",
    "GRASIM.NS", "BAJAJFINSV.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS",
    "BPCL.NS", "HEROMOTOCO.NS", "HINDALCO.NS", "TECHM.NS", "JSWSTEEL.NS",
    "CIPLA.NS", "DRREDDY.NS", "BRITANNIA.NS", "DIVISLAB.NS", "EICHERMOT.NS",
    "SBILIFE.NS", "BAJAJ-AUTO.NS", "TATACONSUM.NS", "APOLLOHOSP.NS",
    "TATASTEEL.NS", "UPL.NS", "INDUSINDBK.NS", "HDFCLIFE.NS", "ICICIPRULI.NS",
    "LTIM.NS", "DMART.NS"
]

# ==============================
# 2️⃣ Indicator & signal logic
# ==============================
def get_signal(stock):
    data = yf.download(stock, period="15d", interval="15m", progress=False)

    if data.empty:
        return None

    data["EMA20"] = ta.trend.EMAIndicator(close=data["Close"].squeeze(), window=20).ema_indicator()
    data["EMA50"] = ta.trend.EMAIndicator(close=data["Close"].squeeze(), window=50).ema_indicator()
    rsi = ta.momentum.RSIIndicator(close=data["Close"].squeeze(), window=14).rsi()

    last_close = data["Close"].iloc[-1]
    last_ema20 = data["EMA20"].iloc[-1]
    last_ema50 = data["EMA50"].iloc[-1]
    last_rsi = rsi.iloc[-1]

    if last_ema20 > last_ema50 and last_rsi < 70:
        return "BUY"
    elif last_ema20 < last_ema50 and last_rsi > 30:
        return "SELL"
    else:
        return None

# ==============================
# 3️⃣ Process stocks & collect signals
# ==============================
signals = []
for stock in nifty50:
    try:
        signal = get_signal(stock)
        if signal:
            signals.append(f"{stock} → {signal}")
    except Exception as e:
        print(f"Error in {stock}: {e}")

# ==============================
# 4️⃣ Log to CSV
# ==============================
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
csv_file = "signal_log.csv"

log_entry = pd.DataFrame({"Time": [timestamp], "Signals": [", ".join(signals)]})
if os.path.exists(csv_file):
    log_entry.to_csv(csv_file, mode="a", header=False, index=False)
else:
    log_entry.to_csv(csv_file, index=False)

# ==============================
# 5️⃣ Calculate accuracy
# ==============================
def calculate_accuracy(csv_file):
    if not os.path.exists(csv_file):
        return 0.0

    df = pd.read_csv(csv_file)
    total_signals = 0
    successful = 0

    for idx, row in df.iterrows():
        sig_list = row['Signals'].split(", ")
        for sig in sig_list:
            total_signals += 1
            stock, action = sig.split(" → ")
            try:
                # check next 15-min candle for profit simulation
                data = yf.download(stock, period="2d", interval="15m", progress=False)
                if data.empty:
                    continue
                if action == "BUY":
                    success = data["Close"].iloc[-1] > data["Close"].iloc[-2]
                else:
                    success = data["Close"].iloc[-1] < data["Close"].iloc[-2]
                if success:
                    successful += 1
            except:
                continue
    return round((successful / total_signals) * 100, 2) if total_signals > 0 else 0.0

accuracy = calculate_accuracy(csv_file)

# ==============================
# 6️⃣ Telegram notification
# ==============================
def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Missing Telegram credentials")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        r = requests.post(url, data=payload)
        print("Telegram response:", r.status_code)
    except Exception as e:
        print("Telegram send failed:", e)

# ==============================
# 7️⃣ Send combined message
# ==============================
if signals:
    msg = f"📊 *Nifty50 Signals*\n\n" + "\n".join(signals)
    msg += f"\n\n📈 Accuracy so far: {accuracy}%"
else:
    msg = f"No signals generated in this cycle.\n📈 Accuracy so far: {accuracy}%"

send_telegram_message(msg)

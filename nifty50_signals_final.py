import yfinance as yf
import pandas as pd
import ta
import requests
import os
from datetime import datetime

# ==============================
# 1️⃣  Define NIFTY 50 stock list
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
# 2️⃣  Define indicator & signal logic
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

    # Basic trading logic
    if last_ema20 > last_ema50 and last_rsi < 70:
        return "BUY"
    elif last_ema20 < last_ema50 and last_rsi > 30:
        return "SELL"
    else:
        return None

# ==============================
# 3️⃣  Process all stocks
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
# 4️⃣  Log to CSV
# ==============================
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
log_entry = pd.DataFrame({"Time": [timestamp], "Signals": [", ".join(signals)]})
csv_file = "signal_log.csv"

if os.path.exists(csv_file):
    log_entry.to_csv(csv_file, mode="a", header=False, index=False)
else:
    log_entry.to_csv(csv_file, index=False)

# ==============================
# 5️⃣  Telegram notification
# ==============================
def send_telegram_message(message):
    """Send message to Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Telegram credentials missing — message not sent.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": message})
        print("✅ Telegram send status:", r.status_code)
    except Exception as e:
        print("❌ Telegram error:", e)

# Combine and send message
if signals:
    msg = "📊 *Nifty50 Combined Signals*\n\n" + "\n".join(signals)
else:
    msg = "No trading signals generated in this cycle."

send_telegram_message(msg)

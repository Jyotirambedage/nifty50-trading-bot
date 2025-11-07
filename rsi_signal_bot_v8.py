import yfinance as yf
import pandas as pd
import numpy as np
import requests
import datetime as dt
import pytz
import os

# =============================
# TELEGRAM SETTINGS
# =============================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(msg):
    """Send Telegram message safely"""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Missing Telegram credentials")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
        print("✅ Message sent to Telegram")
    except Exception as e:
        print("❌ Telegram send failed:", e)

# =============================
# STOCK LIST (NIFTY + BANKNIFTY + SENSEX)
# =============================
NIFTY_50 = [
    "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS","LT.NS",
    "SBIN.NS","AXISBANK.NS","BHARTIARTL.NS","HINDUNILVR.NS","ITC.NS",
    "BAJFINANCE.NS","ADANIGREEN.NS","POWERGRID.NS","NTPC.NS","WIPRO.NS",
    "ULTRACEMCO.NS","TECHM.NS","HCLTECH.NS","MARUTI.NS","KOTAKBANK.NS",
    "TITAN.NS","NESTLEIND.NS","JSWSTEEL.NS","COALINDIA.NS","BPCL.NS",
    "BRITANNIA.NS","HEROMOTOCO.NS","GRASIM.NS","ADANIPORTS.NS","HDFCLIFE.NS",
    "DIVISLAB.NS","DRREDDY.NS","SUNPHARMA.NS","EICHERMOT.NS","TATAMOTORS.NS",
    "TATASTEEL.NS","CIPLA.NS","APOLLOHOSP.NS","BAJAJFINSV.NS","UPL.NS",
    "ONGC.NS","ASIANPAINT.NS","M&M.NS","SBILIFE.NS","BAJAJ-AUTO.NS","INDUSINDBK.NS",
    "HINDALCO.NS","ADANIENT.NS","SHRIRAMFIN.NS","BPCL.NS"
]

BANK_NIFTY = ["HDFCBANK.NS","ICICIBANK.NS","AXISBANK.NS","SBIN.NS","KOTAKBANK.NS","PNB.NS","BANKBARODA.NS"]

SENSEX = [
    "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","BHARTIARTL.NS",
    "HUL.NS","HCLTECH.NS","ASIANPAINT.NS","BAJFINANCE.NS","ITC.NS","LT.NS","M&M.NS",
    "SUNPHARMA.NS","TITAN.NS","ULTRACEMCO.NS","NESTLEIND.NS","TATASTEEL.NS","POWERGRID.NS",
    "HDFCLIFE.NS","NTPC.NS","BAJAJFINSV.NS","MARUTI.NS","WIPRO.NS","TECHM.NS","ONGC.NS",
    "CIPLA.NS","INDUSINDBK.NS","ADANIENT.NS"
]

ALL_STOCKS = list(set(NIFTY_50 + BANK_NIFTY + SENSEX))

# =============================
# MARKET TIME CONTROL
# =============================
IST = pytz.timezone("Asia/Kolkata")
now = dt.datetime.now(IST)
MARKET_OPEN = dt.time(9, 15)
MARKET_CLOSE = dt.time(15, 30)
MARKET_HOURS = MARKET_OPEN <= now.time() <= MARKET_CLOSE

# =============================
# SIGNAL LOG FILE
# =============================
CSV_FILE = "signal_log_v8.csv"
if not os.path.exists(CSV_FILE):
    pd.DataFrame(columns=["datetime","stock","signal","price","rsi","target","stop_loss"]).to_csv(CSV_FILE, index=False)

# =============================
# STRATEGY: RELAXED RSI ONLY
# =============================
def get_signal(stock):
    try:
        data = yf.download(stock, period="5d", interval="15m", progress=False)
        if data.empty or len(data) < 20:
            return None
        data["RSI"] = 100 - (100 / (1 + data["Close"].diff().clip(lower=0).rolling(14).mean() /
                                    (-data["Close"].diff().clip(upper=0).rolling(14).mean()).abs()))
        last_rsi = data["RSI"].iloc[-1]
        price = data["Close"].iloc[-1]

        if last_rsi > 60:   # Relaxed BUY threshold
            return ("BUY", price, round(last_rsi, 2))
        elif last_rsi < 40:  # Relaxed SELL threshold
            return ("SELL", price, round(last_rsi, 2))
        else:
            return None
    except Exception as e:
        print(f"⚠️ Error fetching {stock}: {e}")
        return None

# =============================
# MAIN FUNCTION
# =============================
def main():
    print("🚀 RSI Signal Bot V8 Running...")
    if not MARKET_HOURS:
        print("⏰ Market closed — skipping run.")
        return

    df = pd.read_csv(CSV_FILE)
    new_signals = []

    for stock in ALL_STOCKS:
        signal_data = get_signal(stock)
        if signal_data:
            signal, price, rsi = signal_data
            target = round(price * (1.01 if signal == "BUY" else 0.99), 2)
            stop_loss = round(price * (0.99 if signal == "BUY" else 1.01), 2)

            msg = (
                f"📊 *{signal} SIGNAL ALERT*\n"
                f"🏦 Stock: {stock}\n"
                f"💰 Price: ₹{price:.2f}\n"
                f"📈 RSI: {rsi}\n"
                f"🎯 Target: ₹{target}\n"
                f"⛔ Stop Loss: ₹{stop_loss}\n"
                f"📆 Time: {dt.datetime.now(IST).strftime('%Y-%m-%d %H:%M')}\n"
                f"🏆 Win Chance: ~80%"
            )
            new_signals.append([stock, signal, dt.datetime.now(IST), price, rsi, target, stop_loss])
            send_telegram_message(msg)

    if new_signals:
        new_df = pd.DataFrame(new_signals, columns=["stock","signal","datetime","price","rsi","target","stop_loss"])
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(CSV_FILE, index=False)
        print(f"✅ {len(new_signals)} new signals logged.")
    else:
        print("No new RSI signals detected.")

if __name__ == "__main__":
    main()

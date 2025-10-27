import os
import pandas as pd
import yfinance as yf
import ta
import datetime
import requests
import numpy as np

# =============== CONFIG ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CSV_FILE = "signal_log.csv"

NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "ICICIBANK.NS", "HDFCBANK.NS",
    "SBIN.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "BHARTIARTL.NS",
    "KOTAKBANK.NS", "LT.NS", "ITC.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "ONGC.NS",
    "POWERGRID.NS", "ADANIENT.NS", "NTPC.NS", "NESTLEIND.NS", "WIPRO.NS",
    "JSWSTEEL.NS", "TATASTEEL.NS", "HCLTECH.NS", "BAJAJFINSV.NS",
    "M&M.NS", "COALINDIA.NS"
]

BANK_NIFTY = [
    "HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS",
    "SBIN.NS", "INDUSINDBK.NS", "PNB.NS", "BANKBARODA.NS", "IDFCFIRSTB.NS"
]

# =============== HELPERS ====================
def send_telegram_message(message):
    """Send Telegram notification."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message}
        )
        print(f"📨 Telegram response: {r.status_code}")
    except Exception as e:
        print("❌ Telegram send failed:", e)

def init_csv_if_needed():
    """Ensure CSV file exists and has proper columns."""
    if not os.path.exists(CSV_FILE):
        print("🟡 signal_log.csv not found — creating new one.")
        df = pd.DataFrame(columns=["timestamp", "symbol", "signal", "price", "status", "accuracy"])
        df.to_csv(CSV_FILE, index=False)
    else:
        df = pd.read_csv(CSV_FILE)
        required_cols = ["timestamp", "symbol", "signal", "price", "status", "accuracy"]
        for c in required_cols:
            if c not in df.columns:
                df[c] = ""
        df.to_csv(CSV_FILE, index=False)

def market_is_open():
    """Check if within Indian market hours."""
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    if now.weekday() >= 5:
        return False  # Sat/Sun
    open_time = now.replace(hour=9, minute=15, second=0)
    close_time = now.replace(hour=15, minute=30, second=0)
    return open_time <= now <= close_time

# =============== STRATEGY ====================
def calculate_signal(data):
    """Generate buy/sell/hold based on EMA and RSI."""
    data["EMA20"] = ta.trend.EMAIndicator(data["Close"], 20).ema_indicator()
    data["EMA50"] = ta.trend.EMAIndicator(data["Close"], 50).ema_indicator()
    data["RSI"] = ta.momentum.RSIIndicator(data["Close"], 14).rsi()

    last = data.iloc[-1]
    if last["EMA20"] > last["EMA50"] and last["RSI"] > 60:
        return "BUY"
    elif last["EMA20"] < last["EMA50"] and last["RSI"] < 40:
        return "SELL"
    return "HOLD"

# =============== MAIN ====================
def main():
    print("🚀 Running Nifty + BankNifty signal check...")
    init_csv_if_needed()
    if not market_is_open():
        print("🕒 Market closed — skipping check.")
        return

    all_symbols = list(set(NIFTY_50 + BANK_NIFTY))
    signals = []

    for symbol in all_symbols:
        try:
            data = yf.download(symbol, period="15d", interval="15m", progress=False)
            if data.empty:
                continue
            signal = calculate_signal(data)
            if signal != "HOLD":
                price = round(data["Close"].iloc[-1], 2)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                signals.append({"symbol": symbol, "signal": signal, "price": price, "timestamp": timestamp})
        except Exception as e:
            print(f"❌ Error with {symbol}: {e}")

    if not signals:
        print("✅ No strong signals found this cycle.")
        return

    df = pd.read_csv(CSV_FILE)
    for sig in signals:
        msg = f"{sig['timestamp']} | {sig['symbol']} | {sig['signal']} @ {sig['price']}"
        send_telegram_message(msg)
        df = pd.concat([df, pd.DataFrame([{
            "timestamp": sig["timestamp"],
            "symbol": sig["symbol"],
            "signal": sig["signal"],
            "price": sig["price"],
            "status": "PENDING",
            "accuracy": ""
        }])], ignore_index=True)

    df.to_csv(CSV_FILE, index=False)
    print("✅ Signals logged successfully.")

if __name__ == "__main__":
    main()

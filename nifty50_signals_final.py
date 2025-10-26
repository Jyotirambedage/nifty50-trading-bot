import yfinance as yf
import pandas as pd
import ta
import requests
import os
import datetime
import pytz
import time

# ===============================
# 1. MARKET HOURS CHECK
# ===============================
def is_market_open():
    """Check if Indian stock market is open (Mon–Fri, 9:15–15:30 IST)."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(ist)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

if not is_market_open():
    print("⏸ Market closed — skipping signal check.")
    exit(0)

# ===============================
# 2. TELEGRAM MESSAGE FUNCTION
# ===============================
def send_telegram_message(message):
    """Send message to Telegram using Bot API."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Telegram credentials missing — message not sent.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

    try:
        r = requests.post(url, data=payload)
        print(f"✅ Telegram response: {r.status_code}")
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")

# ===============================
# 3. STOCK LIST
# ===============================
nifty50_stocks = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS",
    "KOTAKBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "AXISBANK.NS", "ULTRACEMCO.NS", "WIPRO.NS", "POWERGRID.NS", "NTPC.NS"
]

# ===============================
# 4. GET SIGNAL FUNCTION
# ===============================
def get_signal(stock):
    try:
        data = yf.download(stock, period="15d", interval="15m", progress=False)

        if data is None or data.empty:
            print(f"⚠️ No data for {stock}")
            return "NO DATA"

        data["EMA20"] = ta.trend.EMAIndicator(data["Close"], 20).ema_indicator()
        data["EMA50"] = ta.trend.EMAIndicator(data["Close"], 50).ema_indicator()
        data["RSI"] = ta.momentum.RSIIndicator(data["Close"], 14).rsi()

        latest = data.iloc[-1]
        prev = data.iloc[-2]

        # Basic crossover + RSI filter logic
        if (
            prev["EMA20"] < prev["EMA50"]
            and latest["EMA20"] > latest["EMA50"]
            and latest["RSI"] < 70
        ):
            return "BUY"
        elif (
            prev["EMA20"] > prev["EMA50"]
            and latest["EMA20"] < latest["EMA50"]
            and latest["RSI"] > 30
        ):
            return "SELL"
        else:
            return "HOLD"
    except Exception as e:
        print(f"Error processing {stock}: {e}")
        return "ERROR"

# ===============================
# 5. MAIN SIGNAL CHECK LOOP
# ===============================
signals = []
now_ist = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M")

for stock in nifty50_stocks:
    signal = get_signal(stock)
    print(f"{stock}: {signal}")
    if signal in ["BUY", "SELL"]:
        signals.append(f"{stock} → {signal}")

# ===============================
# 6. LOG RESULTS LOCALLY
# ===============================
log_file = "signal_log.csv"
df_new = pd.DataFrame([[now_ist, ", ".join(signals) if signals else "No Signal"]],
                      columns=["Timestamp", "Signals"])

if os.path.exists(log_file):
    df_old = pd.read_csv(log_file)
    df_all = pd.concat([df_old, df_new], ignore_index=True)
else:
    df_all = df_new

df_all.to_csv(log_file, index=False)

# ===============================
# 7. SEND TELEGRAM ALERT (only if signals found)
# ===============================
if signals:
    message = "📊 Nifty50 Signals:\n" + "\n".join(signals)
    send_telegram_message(message)
else:
    print("✅ No actionable signals — message not sent.")

print("🏁 Script execution completed successfully.")

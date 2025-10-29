#!/usr/bin/env python3
"""
nifty_banknifty_signals_v4_master.py

Master combined bot:
- INTRADAY (15m)
- SWING (1h)
- OPTION suggestion (via Groww if configured, else yfinance fallback)
- Logs signals to signal_log.csv
- Sends Telegram notifications (manual runs always send a confirmation)
- AUTO_EXECUTE is OFF by default (safe)
"""

import os
import time
from datetime import datetime, timedelta, timezone
import pytz
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import ta

# ---------------- CONFIG ----------------
CSV_FILE = "signal_log.csv"
MARKET_TZ = pytz.timezone("Asia/Kolkata")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROWW_TOKEN = os.getenv("GROWW_ACCESS_TOKEN")  # optional for live option-chain / orders

AUTO_EXECUTE = False   # MUST set True only after careful testing
COOLDOWN_MIN_MINUTES = 45

# Symbol lists (example subset; replace with your full lists)
NIFTY_50 = [
    "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS",
    "LT.NS","SBIN.NS","AXISBANK.NS","BHARTIARTL.NS","HINDUNILVR.NS"
]
BANK_NIFTY = ["HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","AXISBANK.NS","SBIN.NS","PNB.NS","BANKBARODA.NS"]
SYMBOLS = list(dict.fromkeys(NIFTY_50 + BANK_NIFTY))

# ---------------- HELPERS ----------------
def now_ist():
    return datetime.now(timezone.utc).astimezone(MARKET_TZ)

def is_market_open():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    open_dt = n.replace(hour=9, minute=15, second=0, microsecond=0)
    close_dt = n.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_dt <= n <= close_dt

def send_telegram_message(text, parse_markdown=False):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram not configured; message not sent.")
        return False
    payload = {"chat_id": CHAT_ID, "text": text}
    if parse_markdown:
        payload["parse_mode"] = "Markdown"
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload, timeout=15)
        print("Telegram status:", r.status_code)
        return r.ok
    except Exception as e:
        print("Telegram send error:", e)
        return False

def ensure_csv():
    cols = [
        "timestamp","symbol","trade_type","direction","entry","SL","TGT",
        "status","resolved_at","result","option_expiry","option_strike","option_premium",
        "last_signal_ts","notes"
    ]
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=cols)
        df.to_csv(CSV_FILE, index=False)
        print("Created signal_log.csv with headers.")
    else:
        df = pd.read_csv(CSV_FILE)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            for c in missing:
                df[c] = ""
            df.to_csv(CSV_FILE, index=False)
            print("Added missing columns to signal_log.csv:", missing)

def fetch_ohlc(symbol, period="15d", interval="15m"):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
    except Exception as e:
        print("yfinance error:", e)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    for col in ["Open","High","Low","Close","Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(how="all")
    return df

def session_vwap(df):
    if df.empty or not all(c in df.columns for c in ["High","Low","Close","Volume"]):
        return pd.Series(index=df.index, data=np.nan)
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = tp * df["Volume"]
    return pv.cumsum() / df["Volume"].cumsum().replace({0: np.nan})

# ---------------- SIGNAL RULES ----------------
def intraday_rule(symbol):
    """15m intraday relaxed rule: EMA5/EMA20 + RSI + MACD"""
    df = fetch_ohlc(symbol, period="10d", interval="15m")
    if df.empty or len(df) < 50:
        return None
    try:
        df["EMA5"] = ta.trend.EMAIndicator(df["Close"], 5).ema_indicator()
        df["EMA20"] = ta.trend.EMAIndicator(df["Close"], 20).ema_indicator()
        macd = ta.trend.MACD(df["Close"])
        df["MACD"] = macd.macd()
        df["MACD_SIG"] = macd.macd_signal()
        df["RSI"] = ta.momentum.RSIIndicator(df["Close"], 14).rsi()
    except Exception as e:
        print("Indicator error intraday:", e)
        return None

    latest = df.iloc[-2]  # last completed candle
    prev = df.iloc[-3]

    price = float(latest["Close"])
    # relaxed thresholds:
    if (latest["EMA5"] > latest["EMA20"]) and (latest["RSI"] > 50) and (latest["MACD"] > latest["MACD_SIG"]):
        sl = round(price * 0.995, 2)  # ~0.5% SL by default
        tgt = round(price * 1.0075, 2)  # ~0.75% TGT
        return ("BUY", price, sl, tgt, ["EMA5>EMA20","RSI>50","MACD>sig"])
    if (latest["EMA5"] < latest["EMA20"]) and (latest["RSI"] < 50) and (latest["MACD"] < latest["MACD_SIG"]):
        sl = round(price * 1.005, 2)
        tgt = round(price * 0.9925, 2)
        return ("SELL", price, sl, tgt, ["EMA5<EMA20","RSI<50","MACD<sig"])
    return None

def swing_rule(symbol):
    """1h swing rule: EMA20/EMA50 + RSI + MACD"""
    df = fetch_ohlc(symbol, period="120d", interval="60m")
    if df.empty or len(df) < 120:
        return None
    try:
        df["EMA20"] = ta.trend.EMAIndicator(df["Close"], 20).ema_indicator()
        df["EMA50"] = ta.trend.EMAIndicator(df["Close"], 50).ema_indicator()
        macd = ta.trend.MACD(df["Close"])
        df["MACD"] = macd.macd()
        df["MACD_SIG"] = macd.macd_signal()
        df["RSI"] = ta.momentum.RSIIndicator(df["Close"], 14).rsi()
    except Exception as e:
        print("Indicator error swing:", e)
        return None

    latest = df.iloc[-1]
    price = float(latest["Close"])
    if (latest["EMA20"] > latest["EMA50"]) and (latest["RSI"] > 55) and (latest["MACD"] > latest["MACD_SIG"]):
        sl = round(price * 0.98, 2)   # wider SL for swing
        tgt = round(price * 1.04, 2)
        return ("BUY", price, sl, tgt, ["EMA20>EMA50","RSI>55","MACD>sig"])
    if (latest["EMA20"] < latest["EMA50"]) and (latest["RSI"] < 45) and (latest["MACD"] < latest["MACD_SIG"]):
        sl = round(price * 1.02, 2)
        tgt = round(price * 0.96, 2)
        return ("SELL", price, sl, tgt, ["EMA20<EMA50","RSI<45","MACD<sig"])
    return None

# ---------------- OPTION SUGGESTION ----------------
def nearest_friday():
    d = now_ist().date()
    days_ahead = (4 - d.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    expiry = d + timedelta(days=days_ahead)
    return expiry.strftime("%Y-%m-%d")

def get_option_suggestion(symbol, direction, underlying_price):
    """
    Returns (expiry, strike, premium, note)
    - Tries Groww if token available (placeholder), else yfinance fallback.
    """
    expiry = nearest_friday()
    # Try Groww (placeholder)
    if GROWW_TOKEN:
        try:
            # User must implement actual Groww integration here.
            # This is a placeholder to indicate where to call Groww APIs.
            # return (expiry, strike, premium, "groww")
            pass
        except Exception as e:
            print("Groww option error:", e)

    # fallback: yfinance (may

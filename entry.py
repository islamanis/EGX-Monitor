import os
import yfinance as yf
import requests
import time
import pandas as pd
import numpy as np
from datetime import datetime
import schedule

# ==================== الإعدادات من Environment Variables ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

if not TELEGRAM_TOKEN or not CHAT_ID:
    print("❌ خطأ: تأكد من إضافة TELEGRAM_TOKEN و CHAT_ID في Variables")
    raise SystemExit("Missing environment variables")

# ==================== الأسهم ====================
STOCKS = {
    "ABUK.CA": "أبو قير للأسمدة",
    "AMOC.CA": "آموك",
    "ALCN.CA": "الإسكندرية للحاويات",
    "SKPC.CA": "سيدي كرير",
    "MCQE.CA": "أسمنت قنا",
    "MBSC.CA": "أسمنت بني سويف",
    "MPCI.CA": "ممفيس للأدوية",
    "AMES.CA": "المركز الطبي الجديد",
    "EGAL.CA": "مصر للألومنيوم"
}

dynamic_levels = {}
alerted = {}

# ==================== دوال حساب المستويات العلمية ====================

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(period).mean().iloc[-1]
    return atr if not pd.isna(atr) else 0

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

def calculate_pivot_points(df):
    prev = df.iloc[-2]
    pivot = (prev['High'] + prev['Low'] + prev['Close']) / 3
    r1 = (2 * pivot) - prev['Low']
    s1 = (2 * pivot) - prev['High']
    r2 = pivot + (prev['High'] - prev['Low'])
    s2 = pivot - (prev['High'] - prev['Low'])
    return {"pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2}

def get_scientific_levels(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="60d")
        
        if len(df) < 30:
            return None

        current_price = df['Close'].iloc[-1]
        atr = calculate_atr(df)
        rsi = calculate_rsi(df['Close'])
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        
        recent = df.tail(20)
        swing_high = recent['High'].max()
        swing_low = recent['Low'].min()
        
        pivots = calculate_pivot_points(df)
        
        # تحديد الاتجاه
        if sma20 > sma50 and current_price > sma20:
            trend = "صاعد"
        elif sma20 < sma50 and current_price < sma20:
            trend = "هابط"
        else:
            trend = "عرضي"

        if trend in ["صاعد", "عرضي"] and rsi < 68:
            support = max(swing_low, pivots['s1'])
            entry_low = support * 0.995
            entry_high = support * 1.015
            
            mid_entry = (entry_low + entry_high) / 2
            target1 = mid_entry + (1.5 * atr)
            target2 = mid_entry + (2.5 * atr)
            stop = mid_entry - (1.2 * atr)
            stop = min(stop, swing_low * 0.985)
        else:
            entry_low = entry_high = None
            target1 = target2 = None
            stop = current_price - (1.5 * atr)

        return {
            "name": STOCKS[ticker],
            "price": round(float(current_price), 2),
            "atr": round(float(atr), 2),
            "rsi": round(float(rsi), 1),
            "trend": trend,
            "entry_low": round(float(entry_low), 2) if entry_low else None,
            "entry_high": round(float(entry_high), 2) if entry_high else None,
            "target1": round(float(target1), 2) if target1 else None,
            "target2": round(float(target2), 2) if target2 else None,
            "stop": round(float(stop), 2),
            "swing_high": round(float(swing_high), 2),
            "swing_low": round(float(swing_low), 2)
        }
    except Exception as e:
        print(f"Error calculating {ticker}: {e}")
        return None

# ==================== إرسال رسائل تيليجرام ====================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload, timeout=15)
        if response.status_code != 200:
            print(f"Telegram error: {response.text}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

# ==================== تحديث المستويات ====================

def update_all_levels():
    global dynamic_levels
    print(f"[{datetime.now()}] Updating scientific levels...")
    
    message = "📊 <b>تحديث المستويات العلمية اليومية</b>\n"
    message += f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    
    for ticker in STOCKS:
        levels = get_scientific_levels(ticker)
        if levels:
            dynamic_levels[ticker] = levels
            
            msg = f"<b>{levels['name']}</b> ({ticker.replace('.CA','')})\n"
            msg += f"السعر: {levels['price']} | RSI: {levels['rsi']} | اتجاه: {levels['trend']}\n"
            
            if levels['entry_low']:
                msg += f"🟢 دخول: {levels['entry_low']} → {levels['entry_high']}\n"
                msg += f"🎯 هدف1: {levels['target1']} | هدف2: {levels['target2']}\n"
                msg += f"🛑 وقف: {levels['stop']}\n"
            else:
                msg += f"⚠️ لا توجد فرصة شراء حالياً\n"
                msg += f"🛑 وقف مقترح: {levels['stop']}\n"
            
            msg += "────────────\n"
            message += msg
            time.sleep(1.5)
    
    send_telegram(message)
    print("Levels updated and summary sent.")

# ==================== فحص الأسعار ====================

def check_prices():
    for ticker, levels in dynamic_levels.items():
        if not levels.get("entry_low"):
            continue
            
        try:
            stock = yf.Ticker(ticker)
            data = stock.history(period="1d")
            if data.empty:
                continue
                
            price = round(float(data['Close'].iloc[-1]), 2)
            name = levels["name"]
            
            # تنبيه الدخول
            if levels["entry_low"] <= price <= levels["entry_high"]:
                key = f"{ticker}_entry"
                if key not in alerted:
                    send_telegram(
                        f"🟢 <b>فرصة دخول</b>\n"
                        f"{name}\n"
                        f"السعر الحالي: <b>{price}</b>\n"
                        f"منطقة الدخول: {levels['entry_low']} - {levels['entry_high']}\n"
                        f"الهدف 1: {levels['target1']}\n"
                        f"الهدف 2: {levels['target2']}\n"
                        f"الوقف: {levels['stop']}"
                    )
                    alerted[key] = True
            
            # الهدف الأول
            if price >= levels["target1"]:
                key = f"{ticker}_t1"
                if key not in alerted:
                    send_telegram(f"🎯 <b>تحقق الهدف الأول</b>\n{name}\nالسعر: {price}\nالهدف كان: {levels['target1']}")
                    alerted[key] = True
            
            # الهدف الثاني
            if price >= levels["target2"]:
                key = f"{ticker}_t2"
                if key not in alerted:
                    send_telegram(f"🚀 <b>تحقق الهدف الثاني</b>\n{name}\nالسعر: {price}\nالهدف كان: {levels['target2']}")
                    alerted[key] = True
            
            # وقف الخسارة
            if price <= levels["stop"]:
                key = f"{ticker}_stop"
                if key not in alerted:
                    send_telegram(f"🛑 <b>وصول لوقف الخسارة</b>\n{name}\nالسعر: {price}\nالوقف كان: {levels['stop']}")
                    alerted[key] = True
                    
        except Exception as e:
            print(f"Error checking {ticker}: {e}")

# ==================== التشغيل الرئيسي ====================

def main():
    print("Starting EGX Scientific Monitor...")
    send_telegram("✅ <b>بدأت أداة المراقبة العلمية</b>\nالمستويات تُحسب تلقائياً باستخدام ATR + Pivot + RSI + Swing Levels")
    
    # تحديث فوري عند التشغيل
    update_all_levels()
    
    # تحديث يومي الساعة 9:30 صباحاً بتوقيت مصر
    schedule.every().day.at("09:30").do(update_all_levels)
    
    # فحص الأسعار كل دقيقة
    schedule.every(1).minutes.do(check_prices)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

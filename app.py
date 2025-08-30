from flask import Flask, render_template, jsonify
import requests, traceback
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

app = Flask(__name__)

API_KEY = "0f624fe0a0c94db5b7717f73015c9a86"
BASE_URL = "https://api.twelvedata.com/time_series"

# Example NSE F&O stock list (top few, can be expanded)
NSE_FO_STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

def fetch_data(symbol, interval="1day", outputsize=500):
    try:
        url = f"{BASE_URL}?symbol={symbol}&interval={interval}&apikey={API_KEY}&outputsize={outputsize}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if "values" not in data:
            return None
        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime")
        df[["open","high","low","close"]] = df[["open","high","low","close"]].astype(float)
        return df
    except Exception as e:
        print("Error fetching data:", e)
        return None

def detect_cycles(df, max_lag=500):
    try:
        prices = df["close"].values
        cycles = []
        for lag in range(50, max_lag, 50):
            corr = np.corrcoef(prices[:-lag], prices[lag:])[0,1]
            if corr > 0.6:
                cycles.append({"cycle_days": lag, "correlation": float(corr)})
        return cycles
    except Exception as e:
        print("Cycle detection error:", e)
        return []

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan")
def scan():
    results = []
    for stock in NSE_FO_STOCKS:
        try:
            df = fetch_data(stock)
            if df is None: continue
            cycles = detect_cycles(df)
            if not cycles: continue
            best = max(cycles, key=lambda x: x["correlation"])
            last_date = df["datetime"].iloc[-1]
            next_date = last_date + timedelta(days=best["cycle_days"])
            results.append({
                "stock": stock,
                "cycle_days": best["cycle_days"],
                "correlation": round(best["correlation"], 3),
                "last_date": str(last_date.date()),
                "predicted_next_cycle": str(next_date.date())
            })
        except Exception as e:
            results.append({"stock": stock, "error": str(e)})
    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

from flask import Flask, render_template, request, jsonify
import requests, csv, os, traceback
from datetime import datetime
import pytz

app = Flask(__name__)

# ================= CONFIG =================
API_KEY = "0f624fe0a0c94db5b7717f73015c9a86"
BASE_URL = "https://api.twelvedata.com/time_series"
INTERVAL = "1day"
CANDLES = 500  # for Gann cycle analysis
RESULT_FILE = "data/results.csv"

# Example: Split NSE F&O list into chunks of 20
STOCK_LISTS = {
    "List 1": ["RELIANCE", "HDFCBANK", "INFY", "TCS", "ICICIBANK",
               "SBIN", "LT", "AXISBANK", "HINDUNILVR", "KOTAKBANK",
               "BAJFINANCE", "ITC", "BHARTIARTL", "HCLTECH", "WIPRO",
               "ULTRACEMCO", "MARUTI", "SUNPHARMA", "TITAN", "ONGC"],
    "List 2": ["ADANIENT", "ADANIPORTS", "COALINDIA", "POWERGRID", "NTPC",
               "JSWSTEEL", "TATASTEEL", "TECHM", "GRASIM", "BRITANNIA",
               "CIPLA", "DIVISLAB", "EICHERMOT", "HINDALCO", "BAJAJFINSV",
               "HEROMOTOCO", "DRREDDY", "NESTLEIND", "SHREECEM", "M&M"]
    # You can extend with List 3, 4, etc...
}

# ================= HELPERS =================
def fetch_candles(symbol):
    """Fetch candle data from Twelve Data"""
    try:
        url = f"{BASE_URL}?symbol={symbol}&interval={INTERVAL}&outputsize={CANDLES}&apikey={API_KEY}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if "values" not in data:
            return None, f"API error: {data.get('message', 'Unknown error')}"
        return data["values"], None
    except Exception as e:
        return None, str(e)


def analyze_gann_cycle(candles):
    """Dummy Gann cycle detection → replace with real logic"""
    try:
        closes = [float(c["close"]) for c in candles[::-1]]  # oldest → newest
        length = len(closes)

        # Fake cycle logic: assume 90-day cycle
        cycle_length = 90
        last_cycle_start = length - (length % cycle_length)
        next_entry = datetime.now(pytz.timezone("Asia/Kolkata"))
        exit_date = next_entry.replace(day=(next_entry.day % 28) + 1)

        return {
            "cycle_length": cycle_length,
            "next_entry": next_entry.strftime("%Y-%m-%d"),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "trend": "UP" if closes[-1] > closes[-cycle_length] else "DOWN"
        }
    except Exception as e:
        return {"error": str(e)}


def save_result(symbol, result):
    """Save analysis result to CSV"""
    os.makedirs("data", exist_ok=True)
    file_exists = os.path.isfile(RESULT_FILE)
    with open(RESULT_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Symbol", "Cycle Length", "Next Entry", "Exit Date", "Trend", "Timestamp"])
        writer.writerow([
            symbol,
            result.get("cycle_length", ""),
            result.get("next_entry", ""),
            result.get("exit_date", ""),
            result.get("trend", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])


# ================= ROUTES =================
@app.route("/")
def index():
    return render_template("index.html", stock_lists=STOCK_LISTS)


@app.route("/scan", methods=["POST"])
def scan():
    try:
        selected_list = request.form.get("stock_list")
        symbols = STOCK_LISTS.get(selected_list, [])

        results = []
        for sym in symbols:
            candles, err = fetch_candles(sym)
            if err:
                results.append({"symbol": sym, "error": err})
                continue

            analysis = analyze_gann_cycle(candles)
            if "error" in analysis:
                results.append({"symbol": sym, "error": analysis["error"]})
                continue

            save_result(sym, analysis)
            results.append({"symbol": sym, **analysis})

        return jsonify({"status": "ok", "results": results})

    except Exception as e:
        return jsonify({"status": "error", "message": traceback.format_exc()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

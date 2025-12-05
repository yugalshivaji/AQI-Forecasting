import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from dotenv import load_dotenv
from stations import STATION_MAP

# --- LOAD ENV & CONFIGURATION ---
load_dotenv() # Load from local .env file

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# --- CORS MIDDLEWARE (Crucial for separated Frontend/Backend) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTES ---

@app.get("/api/stations")
async def get_stations_list():
    """Returns list of available stations for the dropdown."""
    return {"stations": list(STATION_MAP.keys())}

@app.post("/api/historical-data")
async def get_historical_data(payload: dict = Body(...)):
    station_name = payload.get("station")
    days = int(payload.get("days", 100))
    
    if station_name not in STATION_MAP:
        return {"error": "Station not found"}
        
    lat, lon = STATION_MAP[station_name]
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm2_5&start_date={start_date}&end_date={end_date}&timezone=Asia%2FKolkata"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        hourly_time = data.get('hourly', {}).get('time', [])
        hourly_pm25 = data.get('hourly', {}).get('pm2_5', [])
        
        daily_data = {}
        for time, value in zip(hourly_time, hourly_pm25):
            if value is None: continue
            date_str = time.split("T")[0]
            if date_str not in daily_data:
                daily_data[date_str] = []
            daily_data[date_str].append(value)
            
        result = []
        for date, values in daily_data.items():
            result.append({
                "date": date,
                "min": min(values),
                "max": max(values)
            })
            
        return {"station": station_name, "data": result}
        
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/forecast-data")
async def get_forecast_data(payload: dict = Body(...)):
    station_name = payload.get("station")
    if station_name not in STATION_MAP:
        return {"error": "Station not found"}

    lat, lon = STATION_MAP[station_name]
    
    url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm2_5&forecast_days=5&timezone=Asia%2FKolkata"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        times = data.get('hourly', {}).get('time', [])[:100]
        values = data.get('hourly', {}).get('pm2_5', [])[:100]
        
        result = [{"time": t, "aqi": v} for t, v in zip(times, values)]
        return {"station": station_name, "data": result}
        
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/analyze-policy")
async def analyze_policy(payload: dict = Body(...)):
    if not GEMINI_API_KEY:
        return {"analysis": "<p style='color:red'>Error: GEMINI_API_KEY not found in .env file.</p>"}

    station = payload.get("station")
    hist_data = str(payload.get("historical_summary"))
    
    prompt = f"""
    You are a Chief Environmental Policy Advisor for the Delhi Government.
    
    **Context:** The user is analyzing the station: **{station}**.
    **Recent Data Trend (Last 30 days Min/Max AQI):** {hist_data}
    
    **Task:**
    1. **Pattern Analysis:** Briefly explain the pollution pattern for this specific area (e.g., if it's Anand Vihar, mention bus terminals/heavy traffic; if Okhla, mention industry/waste).
    2. **Policy Recommendations:** Provide 3 concrete, actionable policy recommendations specific to {station} to lower the AQI.
    3. **Health Advisory:** A one-sentence urgent health warning for residents.
    
    **Format:**
    Return clean HTML (using <h5>, <ul>, <li>, <strong>, <p>). Do NOT use markdown backticks.
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return {"analysis": response.text}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    # When running directly, we assume we are inside backend/ or root
    uvicorn.run(app, host="0.0.0.0", port=8000)

import argparse
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import requests
import sqlite3
import os
import time
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(prog="Brookvale Occupancy Server", description="Server for Parking Occupancy")
parser.add_argument("-t", "--token", type=str)
args = parser.parse_args()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

db_file = "carpark_cache.db"

def create_database():
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS carpark_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            current_occupancy INTEGER NOT NULL,
            max_occupancy INTEGER NOT NULL,
            last_updated TEXT NOT NULL
        )
    """)
    connection.commit()
    connection.close()


def get_cached_data(facility):
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()
    cursor.execute(f"SELECT * FROM carpark_data WHERE facility_id = {facility} ORDER BY last_updated DESC")
    result = cursor.fetchone()
    connection.close()

    if not result:
        return None

    data = {
            "facility_id": result[1],
            "timestamp": result[2],
            "current_occupancy": result[3],
            "max_occupancy": result[4],
            "last_updated": result[5],
            }
    return data

def update_cache(facility, output):
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO carpark_data
        (facility_id, timestamp, current_occupancy, max_occupancy, last_updated)
        VALUES (?, ?, ?, ?, datetime('now'))
    """, (facility, output["timestamp"], output["current_occupancy"], output["max_occupancy"]))
    connection.commit()
    connection.close()

def get_carpark_data_from_api(facility):
    url = f"https://api.transport.nsw.gov.au/v1/carpark?facility={facility}"
    headers = {
            "Authorization": f"apikey {args.token}",
            "Accept": "application/json"
        }
    print("Performing API Request!")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        output = {
                "facility_id": data["facility_id"],
                "timestamp": data["MessageDate"],
                "current_occupancy": data["occupancy"]["total"],
                "max_occupancy": data["spots"],
                }
        return output
    else:
        return None

def calc_latest_value(facility: int):
    cached_data = get_cached_data(facility)

    if cached_data:
        last_updated = cached_data["timestamp"]
        time_difference = (time.time() - time.mktime(time.strptime(last_updated, "%Y-%m-%dT%H:%M:%S"))) / 60

        if time_difference < 10:
            return cached_data
        else:
            output = get_carpark_data_from_api(facility)
            if output:
                update_cache(facility, output)
                return output
            else:
                return {"Error": "Failed to get data from API"}
    else:
        output = get_carpark_data_from_api(facility)
        if output:
            update_cache(facility, output)
            return output
        else:
            return {"Error": "Failed to get data from API"}

@app.get("/carpark")
async def get_carpark(facility: int):
    return calc_latest_value(facility)

@app.get("/", response_class=HTMLResponse)
async def get_occupancy(request: Request):
    data = calc_latest_value(490)
    occupancy_percentage = round((int(data["current_occupancy"]) / int(data["max_occupancy"])) * 100, 1)
    return templates.TemplateResponse("occupancy.html", {"request": request, "occupancy_percentage": occupancy_percentage})

if __name__ == "__main__":

    create_database()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


import os
import json
from datetime import date, datetime, timedelta


def load_env(path=".env.local"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key] = value


load_env()

opening_balance = int(os.environ.get("OPENING_BALANCE", "0"))
today = date.today()

with open("cashflow_events.json", encoding="utf-8") as f:
    events = json.load(f)


def event_value(event):
    amount = int(float(event["amount"]))

    if event["direction"] == "outflow":
        return -amount

    return amount


def calculate_balance(days, include_drafts=False):
    end_date = today + timedelta(days=days)
    balance = opening_balance

    for event in events:
        if event.get("needs_confirmation"):
            continue

        due_date_text = event.get("due_date")

        if not due_date_text:
            continue

        due_date = datetime.strptime(
            due_date_text,
            "%Y-%m-%d"
        ).date()

        if not (today <= due_date <= end_date):
            continue

        status = event.get("status")

        if status == "DRAFT" and not include_drafts:
            continue

        balance += event_value(event)

    return balance


result = {
    "forecast_start": str(today),
    "opening_balance": opening_balance,
    "confirmed_forecast": {
        "30_days": calculate_balance(30, False),
        "60_days": calculate_balance(60, False),
        "90_days": calculate_balance(90, False),
    },
    "scenario_including_drafts": {
        "30_days": calculate_balance(30, True),
        "60_days": calculate_balance(60, True),
        "90_days": calculate_balance(90, True),
    },
    "needs_confirmation": [
        event
        for event in events
        if event.get("needs_confirmation")
    ],
}

print(json.dumps(result, indent=2, ensure_ascii=False))

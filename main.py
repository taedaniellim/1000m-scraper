import requests
import re
import json
import os
from datetime import datetime

# Note: dotenv not needed for GitHub Actions - environment variables are loaded automatically

# -------------------------
# CONFIGURATION
# -------------------------
URL = "https://1000mchicago.com/wp-admin/admin-ajax.php"
# UNIT_PATTERN = re.compile(r'^(3[0-9]|4[0-9]|5[0-4])05$')  # Floors 30–54 ending in 05
UNIT_PATTERN = re.compile(r'^\d+$')  # match any numeric unit number
DATA_FILE = "last_statuses.json"

# Pushbullet settings
PUSHBULLET_TOKEN = os.getenv("PUSHBULLET_TOKEN")

# -------------------------
# FUNCTIONS
# -------------------------
def get_unit_statuses():
    """Get unit data from the API and return a dict of {unit: info} for matching units."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://1000mchicago.com/floor-plans/?availability-tabs=apartments-tab"
    }
    
    # POST data matching the form data: action=get_units&floorplan_id=
    data = {
        'action': 'get_units',
        'floorplan_id': ''  # Empty string to get all units across all floor plans
    }
    
    try:
        response = requests.post(URL, headers=headers, data=data)
        response.raise_for_status()
        
        # Parse JSON response
        json_data = response.json()
        
        # Check if the response has the expected structure
        if "units" not in json_data:
            print(f"Unexpected response structure: {json_data}")
            return {}
            
        units = json_data["units"]
        results = {}
        
        for unit in units:
            unit_name = unit.get("name", "")
            
            # Apply unit pattern filter
            if UNIT_PATTERN.match(unit_name):
                # Create a status summary
                status_info = {
                    "name": unit_name,
                    "price": unit.get("price", 0),
                    "beds": unit.get("beds", 0),
                    "baths": unit.get("baths", 0),
                    "sqft": unit.get("sqft", 0),
                    "availableDate": unit.get("availableDate", ""),
                    "amenities": unit.get("amenities", ""),
                    "applyUrl": unit.get("applyUrl", "")
                }
                
                # Create a simple status string for comparison
                status_string = f"Available {status_info['availableDate']} - ${status_info['price']}"
                results[unit_name] = {
                    "status": status_string,
                    "details": status_info
                }
        
        return results
        
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        print(f"Response content: {response.text}")
        return {}

def load_previous_statuses():
    """Load last known statuses from file."""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_statuses(statuses):
    """Save current statuses to file."""
    with open(DATA_FILE, "w") as f:
        json.dump(statuses, f, indent=2)

def send_pushbullet_notification(changed_units):
    """Send a push notification for changed units."""
    if not changed_units:
        return
    
    if not PUSHBULLET_TOKEN:
        print("Warning: PUSHBULLET_TOKEN not set. Skipping notification.")
        return
        
    # Create a more detailed notification
    lines = []
    for unit, data in changed_units.items():
        details = data.get("details", {})
        price = details.get("price", "N/A")
        beds = details.get("beds", "N/A")
        baths = details.get("baths", "N/A")
        sqft = details.get("sqft", "N/A")
        available_date = details.get("availableDate", "N/A")
        
        line = f"Unit {unit}: ${price} | {beds}BR/{baths}BA | {sqft}sqft | Available: {available_date}"
        lines.append(line)
    
    body = "\n".join(lines)
    data = {
        "type": "note", 
        "title": f"1000M Availability Update - {len(changed_units)} units changed", 
        "body": body
    }
    
    try:
        response = requests.post(
            "https://api.pushbullet.com/v2/pushes",
            json=data,
            headers={"Access-Token": PUSHBULLET_TOKEN}
        )
        if response.status_code != 200:
            print(f"Failed to send Pushbullet notification: {response.text}")
        else:
            print("Pushbullet notification sent.")
    except requests.RequestException as e:
        print(f"Failed to send Pushbullet notification: {e}")

# -------------------------
# MAIN
# -------------------------
def main():
    print(f"Checking for updates at {datetime.now()}")
    
    current_statuses = get_unit_statuses()
    if not current_statuses:
        print("No unit data retrieved. Check your request parameters.")
        return
        
    previous_statuses = load_previous_statuses()

    # Find changed units (new units or status changes)
    changed_units = {}
    
    for unit, current_data in current_statuses.items():
        current_status = current_data["status"]
        
        if unit not in previous_statuses:
            # New unit
            changed_units[unit] = current_data
            print(f"New unit detected: {unit}")
        elif current_status != previous_statuses[unit]["status"]:
            # Status changed
            changed_units[unit] = current_data
            print(f"Status changed for unit {unit}")
            print(f"  Old: {previous_statuses[unit]['status']}")
            print(f"  New: {current_status}")

    # Check for units that are no longer available
    for unit in previous_statuses:
        if unit not in current_statuses:
            print(f"Unit {unit} is no longer listed")

    if changed_units:
        print(f"Sending notification for {len(changed_units)} changed units")
        send_pushbullet_notification(changed_units)
    else:
        print("No changes detected.")

    save_statuses(current_statuses)
    print(f"Monitoring {len(current_statuses)} units")

if __name__ == "__main__":
    main()
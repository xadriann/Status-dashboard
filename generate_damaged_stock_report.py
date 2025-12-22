import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import sys
import os
from collections import defaultdict
from config import load_config

# Load global configuration
CONFIG = load_config()
BASE_URL = CONFIG.api_base_url.rstrip('/')

def get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def get_organization_name(token):
    url = f"{BASE_URL}/organization/v1/retrieve"
    response = requests.get(url, headers=get_headers(token))
    response.raise_for_status()
    data = response.json()
    return data.get("own", {}).get("name")

def get_stores(token):
    url = f"{BASE_URL}/organization/v2/list_stores"
    params = {
        "fields[]": ["location", "name", "store_code", "store_type", "sublocations"]
    }
    # Note: If there are many stores, this might need pagination handling depending on API limits.
    # Assuming standard list for now based on prompt.
    response = requests.get(url, headers=get_headers(token), params=params)
    response.raise_for_status()
    return response.json()




# Mapping from disposition to bizStep according to the EPCIS specification
DISPOSITION_TO_BIZSTEP = {
    "urn:epcglobal:cbv:disp:sellable_not_accessible": ["urn:epcglobal:cbv:bizstep:receiving", "urn:epcglobal:cbv:bizstep:unpacking", "urn:epcglobal:cbv:bizstep:cycle_counting"],
    "urn:epcglobal:cbv:disp:sellable_accessible": ["urn:epcglobal:cbv:bizstep:receiving", "urn:epcglobal:cbv:bizstep:unpacking", "urn:epcglobal:cbv:bizstep:stocking", "urn:epcglobal:cbv:bizstep:retail_selling", "urn:epcglobal:cbv:bizstep:cycle_counting"],
    "http://nedapretail.com/disp/sellable_container_closed": ["urn:epcglobal:cbv:bizstep:receiving"],
    "http://nedapretail.com/disp/arrived": ["urn:epcglobal:cbv:bizstep:stocking", "urn:epcglobal:cbv:bizstep:storing", "urn:epcglobal:cbv:bizstep:cycle_counting"],
    "urn:epcglobal:cbv:disp:retail_sold": ["urn:epcglobal:cbv:bizstep:retail_selling"],
    "http://nedapretail.com/disp/online_sold": ["urn:epcglobal:cbv:bizstep:retail_selling"],
    "urn:epcglobal:cbv:disp:active": ["urn:epcglobal:cbv:bizstep:commissioning"],
    "urn:epcglobal:cbv:disp:unknown": ["urn:epcglobal:cbv:bizstep:other", "urn:epcglobal:cbv:bizstep:decommissioning"],
    "urn:epcglobal:cbv:disp:destroyed": ["urn:epcglobal:cbv:bizstep:killing"],
    "urn:epcglobal:cbv:disp:in_progress": ["urn:epcglobal:cbv:bizstep:shipping"],
    "urn:epcglobal:cbv:disp:container_closed": ["urn:epcglobal:cbv:bizstep:shipping"],
    "urn:epcglobal:cbv:disp:in_transit": ["urn:epcglobal:cbv:bizstep:shipping"],
    "urn:epcglobal:cbv:disp:non_sellable_other": ["urn:epcglobal:cbv:bizstep:holding"],
    "http://nedapretail.com/disp/received_order": ["urn:epcglobal:cbv:bizstep:holding"],
    "http://nedapretail.com/disp/retail_reserved": ["http://nedapretail.com/bizstep/retail_reserving"],
    "http://nedapretail.com/disp/retail_reserved_for_peak": ["http://nedapretail.com/bizstep/retail_reserving"],
    "http://nedapretail.com/disp/on_display": ["http://nedapretail.com/bizstep/displaying"],
    "http://nedapretail.com/disp/in_showcase": ["http://nedapretail.com/bizstep/displaying"],
    "http://nedapretail.com/disp/lent": ["http://nedapretail.com/bizstep/lending"],
    "urn:epcglobal:cbv:disp:damaged": ["urn:epcglobal:cbv:bizstep:inspecting"],
    "http://nedapretail.com/disp/faulty": ["urn:epcglobal:cbv:bizstep:inspecting"],
    "http://nedapretail.com/disp/missing_article": ["urn:epcglobal:cbv:bizstep:inspecting"],
    "http://nedapretail.com/disp/customized": ["http://nedapretail.com/bizstep/customizing"],
    "http://nedapretail.com/disp/hemming": ["http://nedapretail.com/bizstep/customizing"],
}

def get_epcis_events(token, location_ids, start_time, end_time, disposition, biz_steps=None):
    """Get EPCIS events where EPCs changed TO the specified disposition"""
    url = f"{BASE_URL}/epcis/v3/query"
    
    # Use provided biz_steps or fallback to default mapping if None passed
    if biz_steps is None:
        biz_steps = DISPOSITION_TO_BIZSTEP.get(disposition)

    # Filter out None values
    valid_locations = [loc for loc in location_ids if loc]
    if not valid_locations:
        return []

    # Format dates to ISO 8601 format - API expects date-time format
    start_str = start_time.isoformat(timespec='seconds')
    end_str = end_time.isoformat(timespec='seconds')
    
    # Build query parameters
    query_params = [
        {"name": "GE_eventTime", "value": start_str},
        {"name": "LT_eventTime", "value": end_str},
        {"name": "EQ_disposition", "values": [disposition]},
        {"name": "EQ_bizStep", "values": biz_steps},
        {"name": "EQ_bizLocation", "values": valid_locations}
    ]
    
    # Add bizStep parameter if we have a mapping for this disposition
    """if biz_steps:
        query_params.append({"name": "EQ_bizStep", "values": [biz_steps]})
    else:
        print(f"Warning: No bizStep mapping found for disposition {disposition}")"""
    
    payload = {
        "parameters": query_params
    }
    
    response = requests.post(url, headers=get_headers(token), json=payload)
    if response.status_code != 200:
        print(f"Warning: Failed to fetch events: {response.text}")
        return []
        
    return response.json().get("events", [])

def get_current_stock(token, store, disposition):
    """Get current RFID stock count for the store's main location (ignoring sublocations)"""
    total_count = 0
    
    location_id = store.get("location")
    if not location_id:
        return 0

    # print(f"Fetching stock count for location {location_id} with disposition {disposition}")
    
    url = f"{BASE_URL}/rfid_stock/v1/retrieve_grouped_by_disposition"
    params = {
        "location": location_id,
        "dispositions[]": disposition
    }
    
    response = requests.get(url, headers=get_headers(token), params=params)
    if response.status_code != 200:
        # print(f"Warning: Failed to fetch stock count: {response.text}")
        return 0
        
    data = response.json()
    stocks = data.get("stocks", [])
    
    # Sum the quantity field from each stock object
    for stock in stocks:
        quantity = stock.get("quantity", 0)
        total_count += quantity
    
    return total_count

def get_total_store_count(token, store):
    """Get total RFID count for the store's main location"""
    location_id = store.get("location")
    if not location_id:
        return 0
    
    url = f"{BASE_URL}/rfid_stock/v1/retrieve_as_gtin14"
    params = {
        "location": location_id
    }
    
    response = requests.get(url, headers=get_headers(token), params=params)
    if response.status_code != 200:
        return 0
        
    data = response.json()
    stocks = data.get("stocks", [])
    
    # Sum all quantity values from the stocks array
    total_quantity = 0
    for stock in stocks:
        total_quantity += stock.get("quantity", 0)
    
    return total_quantity

# List of available dispositions from the documentation
DISPOSITIONS = [
    "urn:epcglobal:cbv:disp:sellable_not_accessible",
    "urn:epcglobal:cbv:disp:sellable_accessible",
    "http://nedapretail.com/disp/sellable_container_closed",
    "http://nedapretail.com/disp/arrived",
    "urn:epcglobal:cbv:disp:retail_sold",
    "http://nedapretail.com/disp/online_sold",
    "urn:epcglobal:cbv:disp:active",
    "urn:epcglobal:cbv:disp:unknown",
    "urn:epcglobal:cbv:disp:destroyed",
    "urn:epcglobal:cbv:disp:in_progress",
    "urn:epcglobal:cbv:disp:container_closed",
    "urn:epcglobal:cbv:disp:in_transit",
    "urn:epcglobal:cbv:disp:non_sellable_other",
    "http://nedapretail.com/disp/received_order",
    "http://nedapretail.com/disp/retail_reserved",
    "http://nedapretail.com/disp/retail_reserved_for_peak",
    "http://nedapretail.com/disp/on_display",
    "http://nedapretail.com/disp/in_showcase",
    "http://nedapretail.com/disp/lent",
    "urn:epcglobal:cbv:disp:damaged",
    "http://nedapretail.com/disp/faulty",
    "http://nedapretail.com/disp/missing_article",
    "http://nedapretail.com/disp/customized",
    "http://nedapretail.com/disp/hemming"
]

def get_sheet_name(disposition_url):
    """Extract sheet name from disposition URL (last word after /)"""
    return disposition_url.split('/')[-1].split(':')[-1]

# Interactive selection functions removed
# All configuration is now loaded from config.json via config.py

def process_disposition(token, stores, disposition, start_time, end_time, biz_steps=None):
    """Process a single disposition and return DataFrame"""
    # Data structure: store_name -> week_str -> count
    data = defaultdict(lambda: defaultdict(int))
    # Store current stock: store_name -> current_count
    current_stock_data = {}
    # Store total counts: store_name -> total_count
    total_store_counts = {}
    all_weeks = set()

    print(f"\nProcessing disposition: {get_sheet_name(disposition)}...")
    
    total_stores = len(stores)
    for i, store in enumerate(stores, 1):
        if i % 10 == 0 or i == total_stores:
            print(f"  Progress: {i}/{total_stores} stores processed...", end='\r')
            if i == total_stores:
                print() # New line when finished
            
        store_name = store.get("name")
        # Collect all locations for this store
        locations_to_check = []
        
        if store.get("location"):
            locations_to_check.append(store.get("location"))
            
        sublocations = store.get("sublocations", [])
        for sub in sublocations:
            locations_to_check.append(sub.get("location"))
        
        # Remove duplicates and None
        locations_to_check = list(set([l for l in locations_to_check if l]))
        
        if not locations_to_check:
            continue

        # Get total store count (all articles)
        total_count = get_total_store_count(token, store)
        if total_count > 0:
            total_store_counts[store_name] = total_count

        # Get current stock for this store (only main location)
        current_count = get_current_stock(token, store, disposition)
        if current_count > 0:
            current_stock_data[store_name] = current_count
        
        # Query events for all locations of this store in one call
        events = get_epcis_events(token, locations_to_check, start_time, end_time, disposition, biz_steps)
        
        for event in events:
            # Get event time to determine the week
            event_time_str = event.get("event_time")
            if event_time_str:
                try:
                    # Parse ISO format
                    event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
                    week_str = event_time.strftime("%Y-W%W")
                    
                    # Count EPCs in this event
                    # Check both epc_list (for object_event) and child_epcs (for aggregation_event)
                    epc_list = event.get("epc_list", [])
                    child_epcs = event.get("child_epcs", [])
                    count = len(epc_list) + len(child_epcs)
                    
                    if count > 0:
                        data[store_name][week_str] += count
                        all_weeks.add(week_str)
                except ValueError as e:
                    pass # Skip if date parse fails

    # Create DataFrame
    sorted_weeks = sorted(list(all_weeks))
    
    if not sorted_weeks and not current_stock_data:
        df = pd.DataFrame(columns=["Store", "Total Articles", "Current Stock", "% of Total"])
    else:
        rows = []
        # Combine stores from both current stock and historical data
        all_stores = set(data.keys()) | set(current_stock_data.keys())
        
        for store_name in all_stores:
            row = {"Store": store_name}
            
            # Add total store count
            total_count = total_store_counts.get(store_name, 0)
            row["Total Articles"] = total_count
            
            # Add current stock with disposition
            current_count = current_stock_data.get(store_name, 0)
            row["Current Stock"] = current_count
            
            # Calculate percentage
            if total_count > 0:
                percentage = (current_count / total_count) * 100
                row["% of Total"] = round(percentage, 2)
            else:
                row["% of Total"] = 0
            
            weeks_data = data.get(store_name, {})
            for week in sorted_weeks:
                row[week] = weeks_data.get(week, 0)
            rows.append(row)
            
        df = pd.DataFrame(rows)
        # Reorder columns: Store, Total Articles, Current Stock, % of Total, then weeks sorted
        cols = ["Store", "Total Articles", "Current Stock", "% of Total"] + sorted_weeks
        if cols[1:]:  # Only reorder if we have data columns
            df = df[cols]
    
    return df

def run_stock_disposition_report(config=None):
    """
    Run the stock disposition report and return DataFrames for each disposition.
    
    Args:
        config: MonitoringConfig object. If None, it will be loaded.
        
    Returns:
        Dict[str, pd.DataFrame]: Mapping of sheet names to DataFrames.
    """
    if config is None:
        config = load_config()
    
    token = config.api_token
    if not token:
        print("Error: API token is not configured.")
        return {}
        
    selected_dispositions = config.stock_report_dispositions
    if not selected_dispositions:
        return {}
    
    # Mapping bizSteps
    disposition_bizsteps = {}
    config_biz_steps = config.stock_report_biz_steps or {}
    for disposition in selected_dispositions:
        if disposition in config_biz_steps:
            biz_steps = config_biz_steps[disposition]
        else:
            biz_steps = DISPOSITION_TO_BIZSTEP.get(disposition)
        disposition_bizsteps[disposition] = biz_steps

    # Get stores
    try:
        stores_data = get_stores(token)
        stores = stores_data if isinstance(stores_data, list) else stores_data.get("stores", [])
    except Exception as e:
        print(f"Error fetching stores: {e}")
        return {}

    # Time range
    end_time = datetime.now(timezone.utc)
    months_to_look_back = config.stock_report_months
    start_time = end_time - timedelta(days=30 * months_to_look_back)
    
    # Process each disposition
    disposition_dataframes = {}
    for disposition in selected_dispositions:
        biz_steps = disposition_bizsteps[disposition]
        df = process_disposition(token, stores, disposition, start_time, end_time, biz_steps)
        sheet_name = get_sheet_name(disposition)
        disposition_dataframes[sheet_name] = df
    
    return disposition_dataframes

def main():
    # Load configuration
    config = load_config()
    
    print("\n" + "="*60)
    print("GENERATING STOCK DISPOSITION REPORT")
    print("="*60)
    
    disposition_dataframes = run_stock_disposition_report(config)
    
    if not disposition_dataframes:
        print("No data generated for report.")
        return

    # Get organization name for filename
    try:
        org_name = get_organization_name(config.api_token)
    except:
        org_name = "Organization"
        
    # Write to Excel
    output_file = f"disposition_report_{org_name}.xlsx"
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for sheet_name, df in disposition_dataframes.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    print(f"\n{'='*60}")
    print(f"Report generated: {output_file}")
    print(f"Created {len(disposition_dataframes)} sheet(s)")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()

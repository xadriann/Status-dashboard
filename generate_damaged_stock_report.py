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

# Biz steps that must always be included in EPCIS queries (enfoque híbrido)
MANDATORY_BIZ_STEPS = [
    "urn:epcglobal:cbv:bizstep:cycle_counting",
    "urn:epcglobal:cbv:bizstep:shipping",
    "urn:epcglobal:cbv:bizstep:receiving",
    "urn:epcglobal:cbv:bizstep:retail_selling"
]

def get_epcis_events(token, location_ids, start_time, end_time, disposition, biz_steps=None):
    """Get EPCIS events where EPCs changed TO the specified disposition"""
    url = f"{BASE_URL}/epcis/v3/query"
    
    # Use provided biz_steps or fallback to default mapping if None passed
    if biz_steps is None:
        biz_steps = DISPOSITION_TO_BIZSTEP.get(disposition)
    
    # Initialize biz_steps list if None or empty
    if not biz_steps:
        biz_steps = []
    elif not isinstance(biz_steps, list):
        biz_steps = [biz_steps]
    
    # Combine disposition-specific biz_steps with mandatory ones (enfoque híbrido)
    # Remove duplicates while preserving order
    all_biz_steps = list(dict.fromkeys(biz_steps + MANDATORY_BIZ_STEPS))

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
        {"name": "EQ_bizStep", "values": all_biz_steps},
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

def get_stock_by_sublocation(token, store, disposition, location_mapper=None):
    """Get current RFID stock count grouped by sublocation type (store, stockroom, sales_floor)"""
    location_id = store.get("location")
    if not location_id:
        return {}, 0
    
    url = f"{BASE_URL}/rfid_stock/v1/retrieve_grouped_by_disposition"
    params = {
        "location": location_id,
        "dispositions[]": disposition
    }
    
    response = requests.get(url, headers=get_headers(token), params=params)
    if response.status_code != 200:
        return {}, 0
        
    data = response.json()
    stocks = data.get("stocks", [])
    
    # Dictionary: sublocation_type -> quantity
    # Keys: "Store", "Stockroom", "Sales Floor"
    stock_by_type = {
        "Store": 0,
        "Stockroom": 0,
        "Sales Floor": 0
    }
    total_count = 0
    
    for stock in stocks:
        quantity = stock.get("quantity", 0)
        stock_location = stock.get("location")
        
        if stock_location:
            # Determine sublocation type
            if stock_location == location_id:
                # This is the main store location
                location_type = "Store"
            else:
                # This is a sublocation - get its type
                if location_mapper:
                    store_info = location_mapper.get_store_info(stock_location)
                    sublocation_type = store_info.get("sublocation_type")
                    
                    if sublocation_type == "stockroom":
                        location_type = "Stockroom"
                    elif sublocation_type == "sales_floor":
                        location_type = "Sales Floor"
                    else:
                        # Unknown type or offsite_storage - could add more types if needed
                        location_type = "Store"  # Default to Store for unknown types
                else:
                    # Without location_mapper, we can't determine type, default to Store
                    location_type = "Store"
            
            # Aggregate by location type
            stock_by_type[location_type] += quantity
            total_count += quantity
    
    # Remove types with zero stock to keep the dictionary clean
    stock_by_type = {k: v for k, v in stock_by_type.items() if v > 0}
    
    return stock_by_type, total_count

def get_stock_by_sublocation_all_dispositions(token, store, dispositions, location_mapper=None):
    """Get current RFID stock count for all dispositions, grouped by disposition and sublocation type"""
    location_id = store.get("location")
    if not location_id or not dispositions:
        return {}
    
    url = f"{BASE_URL}/rfid_stock/v1/retrieve_grouped_by_disposition"
    params = {
        "location": location_id,
        "dispositions[]": dispositions  # Pass array of all dispositions
    }
    
    response = requests.get(url, headers=get_headers(token), params=params)
    if response.status_code != 200:
        return {}
        
    data = response.json()
    stocks = data.get("stocks", [])
    
    # Dictionary: disposition -> {location_type -> quantity}
    # Result structure: {disposition: {"Store": 0, "Stockroom": 0, "Sales Floor": 0}}
    result = {disp: {"Store": 0, "Stockroom": 0, "Sales Floor": 0} for disp in dispositions}
    
    for stock in stocks:
        quantity = stock.get("quantity", 0)
        stock_location = stock.get("location")
        stock_disposition = stock.get("disposition")
        
        if not stock_location or not stock_disposition:
            continue
        
        # Skip if this disposition is not in our list
        if stock_disposition not in result:
            continue
        
        # Determine sublocation type
        if stock_location == location_id:
            # This is the main store location
            location_type = "Store"
        else:
            # This is a sublocation - get its type
            if location_mapper:
                store_info = location_mapper.get_store_info(stock_location)
                sublocation_type = store_info.get("sublocation_type")
                
                if sublocation_type == "stockroom":
                    location_type = "Stockroom"
                elif sublocation_type == "sales_floor":
                    location_type = "Sales Floor"
                else:
                    location_type = "Store"  # Default to Store for unknown types
            else:
                location_type = "Store"
        
        # Aggregate by disposition and location type
        result[stock_disposition][location_type] += quantity
    
    # Remove types with zero stock and dispositions with no stock
    for disp in list(result.keys()):
        result[disp] = {k: v for k, v in result[disp].items() if v > 0}
        if not any(result[disp].values()):
            del result[disp]
    
    return result

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

def process_disposition(token, stores, disposition, start_time, end_time, biz_steps=None, location_mapper=None, store_stock_cache=None):
    """Process a single disposition and return DataFrame aggregated by store (not sublocations)
    
    Args:
        store_stock_cache: Optional dict with pre-fetched stock data by store location
                          Format: {store_location_id: {disposition: {location_type: quantity}}}
    """
    # Mapping: sublocation_id -> store_location_id (to aggregate sublocations to store level)
    sublocation_to_store = {}
    # Data structure: store_location_id -> {store_name, weeks: {week_str -> count}}
    store_data = defaultdict(lambda: {"store_name": None, "weeks": defaultdict(int)})
    # Store current stock: store_location_id -> current_count (aggregated from all sublocations)
    store_current_stock = {}
    # Store stock by sublocation type: store_location_id -> {location_type -> quantity}
    # location_type can be: "Store", "Stockroom", "Sales Floor"
    store_stock_by_sublocation = {}
    # Store total counts: store_location_id -> total_count
    store_total_counts = {}
    all_weeks = set()
    all_location_types = set()  # Track all location types found (Store, Stockroom, Sales Floor)

    print(f"\nProcessing disposition: {get_sheet_name(disposition)}...")
    
    total_stores = len(stores)
    for i, store in enumerate(stores, 1):
        if i % 10 == 0 or i == total_stores:
            print(f"  Progress: {i}/{total_stores} stores processed...", end='\r')
            if i == total_stores:
                print() # New line when finished
            
        store_name = store.get("name")
        store_location = store.get("location")
        
        if not store_location:
            continue
        
        # Map store location to itself
        sublocation_to_store[store_location] = store_location
        store_data[store_location]["store_name"] = store_name
        
        # Get total store count (all articles) - this is at store level
        total_count = get_total_store_count(token, store)
        if total_count > 0:
            store_total_counts[store_location] = total_count
        
        # Collect all locations for this store (including sublocations)
        locations_to_check = [store_location]
        
        # Map sublocations to store location and collect them
        sublocations = store.get("sublocations", [])
        for sub in sublocations:
            sublocation_location = sub.get("location")
            if sublocation_location:
                locations_to_check.append(sublocation_location)
                # Map sublocation to its parent store location
                sublocation_to_store[sublocation_location] = store_location
        
        # Remove duplicates and None
        locations_to_check = list(set([l for l in locations_to_check if l]))
        
        if not locations_to_check:
            continue
        
        # Get current stock grouped by sublocation type for the store
        # Always use cache (should be pre-fetched in run_stock_disposition_report)
        if store_stock_cache and store_location in store_stock_cache:
            stock_data = store_stock_cache[store_location].get(disposition, {})
            stock_by_type = stock_data.copy()
            total_stock = sum(stock_by_type.values())
        else:
            # If cache is not available, return empty (should not happen if called correctly)
            stock_by_type = {}
            total_stock = 0
        
        if total_stock > 0:
            store_current_stock[store_location] = total_stock
            store_stock_by_sublocation[store_location] = stock_by_type
            # Track all location types for column generation
            all_location_types.update(stock_by_type.keys())
        
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
                    
                    # Get location from event (biz_location or read_point)
                    event_location = event.get("biz_location") or event.get("read_point")
                    if not event_location:
                        continue
                    
                    # Map event location to store location (aggregate sublocations)
                    store_location_for_event = sublocation_to_store.get(event_location)
                    if not store_location_for_event:
                        continue
                    
                    # Count EPCs in this event
                    # Check both epc_list (for object_event) and child_epcs (for aggregation_event)
                    epc_list = event.get("epc_list", [])
                    child_epcs = event.get("child_epcs", [])
                    count = len(epc_list) + len(child_epcs)
                    
                    if count > 0:
                        # Aggregate to store level
                        store_data[store_location_for_event]["weeks"][week_str] += count
                        all_weeks.add(week_str)
                except ValueError as e:
                    pass # Skip if date parse fails

    # Create DataFrame - one row per store
    sorted_weeks = sorted(list(all_weeks))
    
    if not sorted_weeks and not store_current_stock:
        df = pd.DataFrame(columns=["Store Name", "Store Location ID", "Total Articles", "Current Stock", "% of Total"])
    else:
        rows = []
        # Get all store locations
        all_store_locations = set(store_data.keys()) | set(store_current_stock.keys())
        
        for store_location_id in all_store_locations:
            store_info_data = store_data.get(store_location_id, {})
            store_name = store_info_data.get("store_name")
            
            # If location_mapper is available, use it to get store name
            if location_mapper:
                store_info = location_mapper.get_store_info(store_location_id)
                store_name = store_info.get("store_name") or store_name
            
            row = {
                "Store Name": store_name or "",
                "Store Location ID": store_location_id
            }
            
            # Add total store count
            total_count = store_total_counts.get(store_location_id, 0)
            row["Total Articles"] = total_count
            
            # Add current stock with disposition (aggregated from all sublocations)
            current_count = store_current_stock.get(store_location_id, 0)
            row["Current Stock"] = current_count
            
            # Calculate percentage
            if total_count > 0:
                percentage = (current_count / total_count) * 100
                row["% of Total"] = round(percentage, 2)
            else:
                row["% of Total"] = 0
            
            # Add stock distribution by location type
            stock_by_type = store_stock_by_sublocation.get(store_location_id, {})
            # Define order: Store, Stockroom, Sales Floor
            location_type_order = ["Store", "Stockroom", "Sales Floor"]
            for location_type in location_type_order:
                if location_type in all_location_types:
                    # Column name: "Stock: {location_type}"
                    col_name = f"Stock: {location_type}"
                    row[col_name] = stock_by_type.get(location_type, 0)
            
            # Add weekly data (aggregated from all sublocations)
            weeks_data = store_info_data.get("weeks", {})
            for week in sorted_weeks:
                row[week] = weeks_data.get(week, 0)
            rows.append(row)
            
        df = pd.DataFrame(rows)
        # Reorder columns: Store Name, Store Location ID, Total Articles, Current Stock, % of Total, 
        # then location type columns in order (Store, Stockroom, Sales Floor), then weeks sorted
        location_type_order = ["Store", "Stockroom", "Sales Floor"]
        location_type_cols = [f"Stock: {loc_type}" for loc_type in location_type_order if loc_type in all_location_types]
        cols = ["Store Name", "Store Location ID", "Total Articles", "Current Stock", "% of Total"] + location_type_cols + sorted_weeks
        if cols[1:]:  # Only reorder if we have data columns
            df = df[cols]
    
    return df

def run_stock_disposition_report(config=None, location_mapper=None):
    """
    Run the stock disposition report and return DataFrames for each disposition.
    
    Args:
        config: MonitoringConfig object. If None, it will be loaded.
        location_mapper: LocationMapper instance for translating location IDs to names.
        
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
    
    # Filter stores based on configuration
    original_store_count = len(stores)
    
    if config.stock_report_store_codes:
        # Filter by store codes
        stores = [s for s in stores if s.get("store_code") in config.stock_report_store_codes]
        print(f"Filtered to {len(stores)} store(s) by store codes: {config.stock_report_store_codes}")
    
    elif config.stock_report_store_locations:
        # Filter by location IDs
        stores = [s for s in stores if s.get("location") in config.stock_report_store_locations]
        print(f"Filtered to {len(stores)} store(s) by location IDs: {config.stock_report_store_locations}")
    
    if config.stock_report_store_limit and config.stock_report_store_limit > 0:
        # Limit number of stores
        stores = stores[:config.stock_report_store_limit]
        if len(stores) < original_store_count:
            print(f"Limited to first {len(stores)} store(s) (from {original_store_count} total)")
    
    if not stores:
        print("No stores to process after filtering.")
        return {}

    # Time range
    end_time = datetime.now(timezone.utc)
    months_to_look_back = config.stock_report_months
    start_time = end_time - timedelta(days=30 * months_to_look_back)
    
    # Pre-fetch stock data for all dispositions in one call per store
    print("\nFetching stock data for all dispositions...")
    store_stock_cache = {}  # {store_location_id: {disposition: {location_type: quantity}}}
    
    total_stores = len(stores)
    for i, store in enumerate(stores, 1):
        if i % 10 == 0 or i == total_stores:
            print(f"  Stock fetch progress: {i}/{total_stores} stores...", end='\r')
            if i == total_stores:
                print()  # New line when finished
        
        store_location = store.get("location")
        if not store_location:
            continue
        
        temp_store = {"location": store_location}
        stock_data = get_stock_by_sublocation_all_dispositions(token, temp_store, selected_dispositions, location_mapper)
        if stock_data:
            store_stock_cache[store_location] = stock_data
    
    print("Stock data fetched. Processing dispositions...")
    
    # Process each disposition (using cached stock data)
    disposition_dataframes = {}
    for disposition in selected_dispositions:
        biz_steps = disposition_bizsteps[disposition]
        df = process_disposition(token, stores, disposition, start_time, end_time, biz_steps, location_mapper, store_stock_cache)
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

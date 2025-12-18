"""
Metrics module for damaged items in shipments.
Calculates metrics per store for damaged items shipped.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict

from models import EPCISEvent
from api_client import IDCloudAPIClient


@dataclass
class StoreShipmentMetrics:
    """Metrics for damaged items in shipments per store."""
    location: str
    total_epcs_affected: int  # Total EPCs across all time
    total_epcs_last_week: int  # Total EPCs in last 7 days
    events_count: int  # Number of shipping events
    events_last_week: int  # Number of events in last week
    first_occurrence: Optional[datetime] = None
    last_occurrence: Optional[datetime] = None


def calculate_shipment_metrics(
    events: List[EPCISEvent],
    week_start: Optional[datetime] = None
) -> Dict[str, StoreShipmentMetrics]:
    """
    Calculate metrics per store for damaged items in shipments.
    
    Args:
        events: List of EPCIS events (shipping with damaged disposition)
        week_start: Start of the week period (default: 7 days ago)
    
    Returns:
        Dictionary mapping location URN to StoreShipmentMetrics
    """
    if week_start is None:
        week_start = datetime.now(timezone.utc) - timedelta(days=7)
    
    # Ensure week_start is timezone-aware (UTC)
    if week_start.tzinfo is None:
        week_start = week_start.replace(tzinfo=timezone.utc)
    
    metrics_by_location: Dict[str, StoreShipmentMetrics] = {}
    location_epcs: Dict[str, set] = defaultdict(set)  # location -> set of unique EPCs
    location_epcs_week: Dict[str, set] = defaultdict(set)  # location -> set of EPCs in last week
    location_events: Dict[str, List[EPCISEvent]] = defaultdict(list)
    location_first: Dict[str, datetime] = {}
    location_last: Dict[str, datetime] = {}
    
    for event in events:
        location = event.get_location()
        if not location:
            continue
        
        # Normalize event_time to UTC if it's timezone-aware
        event_time_utc = event.event_time
        if event_time_utc.tzinfo is None:
            # If naive, assume UTC
            event_time_utc = event_time_utc.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC
            event_time_utc = event_time_utc.astimezone(timezone.utc)
        
        # Track all EPCs for this location
        for epc in event.epc_list:
            location_epcs[location].add(epc)
            
            # Track EPCs in last week
            if event_time_utc >= week_start:
                location_epcs_week[location].add(epc)
        
        # Track events
        location_events[location].append(event)
        
        # Track first and last occurrence (using normalized time)
        if location not in location_first or event_time_utc < location_first[location]:
            location_first[location] = event_time_utc
        
        if location not in location_last or event_time_utc > location_last[location]:
            location_last[location] = event_time_utc
    
    # Build metrics objects
    for location in location_epcs.keys():
        events_in_week = [
            e for e in location_events[location]
            if (e.event_time.replace(tzinfo=timezone.utc) if e.event_time.tzinfo is None 
                else e.event_time.astimezone(timezone.utc)) >= week_start
        ]
        
        metrics_by_location[location] = StoreShipmentMetrics(
            location=location,
            total_epcs_affected=len(location_epcs[location]),
            total_epcs_last_week=len(location_epcs_week[location]),
            events_count=len(location_events[location]),
            events_last_week=len(events_in_week),
            first_occurrence=location_first.get(location),
            last_occurrence=location_last.get(location)
        )
    
    return metrics_by_location


def fetch_and_calculate_metrics(
    api_client: IDCloudAPIClient,
    week_start: Optional[datetime] = None
) -> Dict[str, StoreShipmentMetrics]:
    """
    Fetch damaged items in shipments from API and calculate metrics.
    
    Args:
        api_client: Initialized IDCloudAPIClient
        week_start: Start of the week period (default: 7 days ago)
    
    Returns:
        Dictionary mapping location URN to StoreShipmentMetrics
    """
    if week_start is None:
        week_start = datetime.now(timezone.utc) - timedelta(days=7)
    
    # Ensure week_start is timezone-aware
    if week_start.tzinfo is None:
        week_start = week_start.replace(tzinfo=timezone.utc)
    
    now_utc = datetime.now(timezone.utc)
    print(f"Fetching all damaged items in shipments...")
    print(f"Week period: {week_start.isoformat()} to {now_utc.isoformat()}")
    
    # Fetch all events (no time limit for total, but filter for week)
    all_events = api_client.fetch_all_damaged_in_shipments()
    
    print(f"Fetched {len(all_events)} total events")
    
    # Calculate metrics
    metrics = calculate_shipment_metrics(all_events, week_start)
    
    return metrics


def print_metrics_report(metrics: Dict[str, StoreShipmentMetrics]):
    """Print a formatted report of shipment metrics."""
    if not metrics:
        print("\nNo damaged items found in shipments.")
        return
    
    print("\n" + "=" * 100)
    print("DAMAGED ITEMS IN SHIPMENTS - METRICS BY STORE")
    print("=" * 100)
    print(f"\n{'Location':<50} {'Total EPCs':<15} {'Last Week EPCs':<18} {'Events':<10} {'Week Events':<12}")
    print("-" * 100)
    
    # Sort by total EPCs affected (descending)
    sorted_metrics = sorted(
        metrics.values(),
        key=lambda m: m.total_epcs_affected,
        reverse=True
    )
    
    for metric in sorted_metrics:
        print(f"{metric.location:<50} {metric.total_epcs_affected:<15} "
              f"{metric.total_epcs_last_week:<18} {metric.events_count:<10} "
              f"{metric.events_last_week:<12}")
    
    print("\n" + "=" * 100)
    print(f"\nTotal stores affected: {len(metrics)}")
    total_epcs = sum(m.total_epcs_affected for m in metrics.values())
    total_epcs_week = sum(m.total_epcs_last_week for m in metrics.values())
    print(f"Total unique EPCs affected (all time): {total_epcs}")
    print(f"Total unique EPCs affected (last week): {total_epcs_week}")
    print("=" * 100 + "\n")


def export_metrics_to_json(
    metrics: Dict[str, StoreShipmentMetrics],
    output_file: str = "shipment_metrics.json"
) -> str:
    """Export metrics to JSON file."""
    import json
    
    metrics_data = {
        "generated_at": datetime.utcnow().isoformat(),
        "stores": [
            {
                "location": m.location,
                "total_epcs_affected": m.total_epcs_affected,
                "total_epcs_last_week": m.total_epcs_last_week,
                "events_count": m.events_count,
                "events_last_week": m.events_last_week,
                "first_occurrence": m.first_occurrence.isoformat() if m.first_occurrence else None,
                "last_occurrence": m.last_occurrence.isoformat() if m.last_occurrence else None
            }
            for m in metrics.values()
        ],
        "summary": {
            "total_stores": len(metrics),
            "total_epcs_all_time": sum(m.total_epcs_affected for m in metrics.values()),
            "total_epcs_last_week": sum(m.total_epcs_last_week for m in metrics.values())
        }
    }
    
    with open(output_file, "w") as f:
        json.dump(metrics_data, f, indent=2, default=str)
    
    return output_file


def get_metrics_dataframe(metrics: Dict[str, StoreShipmentMetrics]) -> Any:
    """Convert shipment metrics to a Pandas DataFrame."""
    import pandas as pd
    rows = []
    for m in metrics.values():
        rows.append({
            "Location": m.location,
            "Total EPCs Affected (All Time)": m.total_epcs_affected,
            "Total EPCs Affected (Last Week)": m.total_epcs_last_week,
            "Total Shipping Events": m.events_count,
            "Shipping Events (Last Week)": m.events_last_week,
            "First Occurrence": m.first_occurrence,
            "Last Occurrence": m.last_occurrence
        })
    return pd.DataFrame(rows)


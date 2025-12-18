"""
Example script showing how to use the iD Cloud API client.
"""
from datetime import datetime, timedelta
from api_client import IDCloudAPIClient
from processor import EventProcessor
from alerter import AlertManager, ConsoleAlertHandler
from dashboard import Dashboard
from config import MonitoringConfig


def example_query_damaged_events():
    """Example: Query damaged events from API."""
    print("=" * 80)
    print("Example: Querying Damaged Events from iD Cloud API")
    print("=" * 80)
    
    # Initialize API client
    # NOTE: Replace with your actual API token
    api_token = "YOUR_API_TOKEN_HERE"
    
    if api_token == "YOUR_API_TOKEN_HERE":
        print("\n⚠️  Please set your API token in this script!")
        print("   Get your token from iD Cloud developer portal")
        return
    
    client = IDCloudAPIClient(
        base_url="https://api.nedapretail.com",  # or "https://api.nedapretail.us" for US
        api_token=api_token
    )
    
    # Query damaged events from last 24 hours
    print("\n📡 Fetching damaged events from last 24 hours...")
    from_time = datetime.utcnow() - timedelta(hours=24)
    
    try:
        events = client.fetch_all_damaged_events(
            from_time=from_time,
            max_events=100  # Limit to first 100 events
        )
        
        print(f"✅ Fetched {len(events)} damaged events")
        
        # Process events
        if events:
            print("\n🔍 Processing events for misuse detection...")
            config = MonitoringConfig()
            processor = EventProcessor()
            alert_manager = AlertManager()
            alert_manager.add_handler(ConsoleAlertHandler())
            dashboard = Dashboard(processor)
            
            alerts = processor.process_events(events)
            if alerts:
                alert_manager.send_alerts(alerts)
            
            print(f"\n📊 Summary: {len(alerts)} alerts generated from {len(events)} events")
            dashboard.print_dashboard()
        
    except Exception as e:
        print(f"❌ Error: {e}")


def example_query_by_location():
    """Example: Query events for a specific location."""
    print("\n" + "=" * 80)
    print("Example: Querying Events by Location")
    print("=" * 80)
    
    api_token = "YOUR_API_TOKEN_HERE"
    
    if api_token == "YOUR_API_TOKEN_HERE":
        print("\n⚠️  Please set your API token!")
        return
    
    client = IDCloudAPIClient(
        base_url="https://api.nedapretail.com",
        api_token=api_token
    )
    
    # Example location URN
    location = "urn:epc:id:sgln:0012345.11111.0"
    
    print(f"\n📡 Fetching events for location: {location}")
    
    try:
        response = client.query_damaged_events(
            location=location,
            from_time=datetime.utcnow() - timedelta(hours=24)
        )
        
        events_data = response.get("events", [])
        print(f"✅ Found {len(events_data)} events")
        
        if events_data:
            print("\n📋 Sample event:")
            print(f"   ID: {events_data[0].get('id')}")
            print(f"   Time: {events_data[0].get('event_time')}")
            print(f"   Disposition: {events_data[0].get('disposition')}")
            print(f"   EPCs: {len(events_data[0].get('epc_list', []))}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def example_query_by_biz_step():
    """Example: Query events by business step."""
    print("\n" + "=" * 80)
    print("Example: Querying Events by Business Step")
    print("=" * 80)
    
    api_token = "YOUR_API_TOKEN_HERE"
    
    if api_token == "YOUR_API_TOKEN_HERE":
        print("\n⚠️  Please set your API token!")
        return
    
    client = IDCloudAPIClient(
        base_url="https://api.nedapretail.com",
        api_token=api_token
    )
    
    # Query inspection events (which can mark items as damaged)
    biz_step = "urn:epcglobal:cbv:bizstep:inspecting"
    
    print(f"\n📡 Fetching inspection events...")
    
    try:
        response = client.query_events_by_biz_step(
            biz_step=biz_step,
            from_time=datetime.utcnow() - timedelta(hours=24)
        )
        
        events_data = response.get("events", [])
        print(f"✅ Found {len(events_data)} inspection events")
        
        # Count how many resulted in damaged disposition
        damaged_count = sum(
            1 for e in events_data 
            if e.get("disposition") == "urn:epcglobal:cbv:disp:damaged"
        )
        print(f"   📊 {damaged_count} resulted in damaged disposition")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def example_custom_query():
    """Example: Custom query with multiple parameters."""
    print("\n" + "=" * 80)
    print("Example: Custom Query with Multiple Parameters")
    print("=" * 80)
    
    api_token = "YOUR_API_TOKEN_HERE"
    
    if api_token == "YOUR_API_TOKEN_HERE":
        print("\n⚠️  Please set your API token!")
        return
    
    client = IDCloudAPIClient(
        base_url="https://api.nedapretail.com",
        api_token=api_token
    )
    
    # Custom query: damaged events in shipping
    print("\n📡 Querying damaged items in shipments...")
    
    parameters = [
        {
            "name": "EQ_disposition",
            "value": "urn:epcglobal:cbv:disp:damaged"
        },
        {
            "name": "EQ_bizStep",
            "value": "urn:epcglobal:cbv:bizstep:shipping"
        },
        {
            "name": "GE_eventTime",
            "value": (datetime.utcnow() - timedelta(hours=24)).isoformat()
        }
    ]
    
    try:
        response = client.query_epcis_events(
            parameters=parameters,
            use_cursor=True,
            event_count_limit=50
        )
        
        events_data = response.get("events", [])
        print(f"✅ Found {len(events_data)} damaged items in shipments")
        
        if events_data:
            print("\n⚠️  This could indicate Rule 1 violation!")
            print("   (Damaged items should not be in regular shipments)")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("iD Cloud API Client Examples")
    print("=" * 80)
    print("\n⚠️  IMPORTANT: Set your API token in this script before running!")
    print("   Get your token from: https://developer.nedapretail.com/")
    print("\n" + "=" * 80)
    
    # Uncomment the example you want to run:
    
    # example_query_damaged_events()
    # example_query_by_location()
    # example_query_by_biz_step()
    # example_custom_query()
    
    print("\n💡 Uncomment an example function above to run it!")


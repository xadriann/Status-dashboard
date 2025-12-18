"""
Example script demonstrating the monitoring system.
"""
from datetime import datetime
from models import EPCISEvent, EventType, DispositionStatus
from processor import EventProcessor
from alerter import AlertManager, ConsoleAlertHandler
from dashboard import Dashboard
from config import MonitoringConfig


def create_test_events():
    """Create sample test events that should trigger various alerts."""
    events = [
        # Rule 1: Damaged item in regular shipment
        EPCISEvent(
            event_id="TEST-001",
            event_type=EventType.DISPOSITION_CHANGE,
            timestamp=datetime.now(),
            epc="EPC-001",
            location="Store-001",
            disposition=DispositionStatus.DAMAGED,
            previous_disposition=DispositionStatus.AVAILABLE
        ),
        EPCISEvent(
            event_id="TEST-002",
            event_type=EventType.SHIPMENT_ADD,
            timestamp=datetime.now(),
            epc="EPC-001",
            location="Store-001",
            disposition=DispositionStatus.DAMAGED,
            shipment_type="Regular",
            shipment_id="SHIP-001"
        ),
        
        # Rule 6: Damaged item sold at POS
        EPCISEvent(
            event_id="TEST-003",
            event_type=EventType.DISPOSITION_CHANGE,
            timestamp=datetime.now(),
            epc="EPC-002",
            location="Store-002",
            disposition=DispositionStatus.DAMAGED,
            previous_disposition=DispositionStatus.AVAILABLE
        ),
        EPCISEvent(
            event_id="TEST-004",
            event_type=EventType.POS_SALE,
            timestamp=datetime.now(),
            epc="EPC-002",
            location="Store-002",
            metadata={"transaction_id": "TXN-001", "sale_amount": 29.99}
        ),
        
        # Rule 3: Damaged status overwritten
        EPCISEvent(
            event_id="TEST-005",
            event_type=EventType.DISPOSITION_CHANGE,
            timestamp=datetime.now(),
            epc="EPC-003",
            location="Store-003",
            disposition=DispositionStatus.RESERVED_FOR_PEAK,
            previous_disposition=DispositionStatus.DAMAGED,
            metadata={"bulk_operation": True}
        ),
        
        # Rule 8: Damaged item in wrong sublocation
        EPCISEvent(
            event_id="TEST-006",
            event_type=EventType.DISPOSITION_CHANGE,
            timestamp=datetime.now(),
            epc="EPC-004",
            location="Store-004",
            sublocation="Sales Floor",
            disposition=DispositionStatus.DAMAGED,
            previous_disposition=DispositionStatus.AVAILABLE
        ),
        
        # Rule 9: Sold item returned as damaged
        EPCISEvent(
            event_id="TEST-007",
            event_type=EventType.DISPOSITION_CHANGE,
            timestamp=datetime.now(),
            epc="EPC-005",
            location="Store-005",
            disposition=DispositionStatus.RETAIL_SOLD,
            previous_disposition=DispositionStatus.AVAILABLE
        ),
        EPCISEvent(
            event_id="TEST-008",
            event_type=EventType.DISPOSITION_CHANGE,
            timestamp=datetime.now(),
            epc="EPC-005",
            location="Store-005",
            disposition=DispositionStatus.DAMAGED,
            previous_disposition=DispositionStatus.RETAIL_SOLD
        ),
        
        # Rule 11: Double stock deduction
        EPCISEvent(
            event_id="TEST-009",
            event_type=EventType.DISPOSITION_CHANGE,
            timestamp=datetime.now(),
            epc="EPC-006",
            location="Store-006",
            disposition=DispositionStatus.DAMAGED,
            previous_disposition=DispositionStatus.AVAILABLE
        ),
        EPCISEvent(
            event_id="TEST-010",
            event_type=EventType.POS_SALE,
            timestamp=datetime.now(),
            epc="EPC-006",
            location="Store-006",
            metadata={"transaction_id": "TXN-002", "sale_amount": 39.99}
        ),
    ]
    return events


def main():
    """Run example test."""
    print("=" * 80)
    print("EPC DISPOSITION MISUSE MONITORING - TEST EXAMPLE")
    print("=" * 80)
    
    # Create test events
    events = create_test_events()
    print(f"\nCreated {len(events)} test events\n")
    
    # Initialize system
    config = MonitoringConfig()
    processor = EventProcessor()
    alert_manager = AlertManager()
    alert_manager.add_handler(ConsoleAlertHandler())
    dashboard = Dashboard(processor)
    
    # Process events
    print("Processing events...\n")
    for event in events:
        alerts = processor.process_event(event)
        if alerts:
            alert_manager.send_alerts(alerts)
    
    # Show summary
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: Generated {len(processor.alerts)} alerts from {len(events)} events")
    print(f"{'=' * 80}\n")
    
    # Show dashboard
    dashboard.print_dashboard()
    
    # Generate report
    report = dashboard.generate_report("test_report.json")
    print(f"\nReport saved to: test_report.json")


if __name__ == "__main__":
    main()


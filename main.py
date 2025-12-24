"""
Main entry point for damaged status misuse monitoring system.
"""
import os
import sys
import json
import argparse
from typing import List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd

from models import EPCISEvent, AlertSeverity
from processor import EventProcessor, EPCISEventParser
from alerter import AlertManager, ConsoleAlertHandler, FileAlertHandler, EmailAlertHandler, WebhookAlertHandler
from dashboard import Dashboard
from config import MonitoringConfig, load_config
from api_client import IDCloudAPIClient
from shipment_metrics import fetch_and_calculate_metrics, print_metrics_report, export_metrics_to_json, get_metrics_dataframe
from generate_damaged_stock_report import run_stock_disposition_report
from location_mapper import LocationMapper


def serialize_event_to_dict(event: EPCISEvent) -> Dict[str, Any]:
    """Convert EPCISEvent to dictionary for JSON serialization."""
    return {
        "id": event.id,
        "type": event.type.value,
        "action": event.action.value,
        "event_time": event.event_time.isoformat(),
        "event_time_zone_offset": event.event_time_zone_offset,
        "record_time": event.record_time.isoformat() if event.record_time else None,
        "disposition": event.disposition,
        "biz_step": event.biz_step,
        "biz_location": event.biz_location,
        "read_point": event.read_point,
        "epc_list": event.epc_list,
        "quantity_list": event.quantity_list,
        "biz_transaction_list": event.biz_transaction_list,
        "source_list": event.source_list,
        "destination_list": event.destination_list,
        "error_declaration": event.error_declaration,
        "stored_id": event.stored_id,
        "event_id": event.event_id,
        "metadata": event.metadata
    }


class MonitoringSystem:
    """Main monitoring system coordinator."""
    
    def __init__(self, config: MonitoringConfig, location_mapper: LocationMapper = None):
        self.config = config
        self.location_mapper = location_mapper
        self.processor = EventProcessor(location_mapper=location_mapper)
        self.alert_manager = AlertManager()
        self.dashboard = Dashboard(self.processor, location_mapper=location_mapper)
        self._setup_alert_handlers()
    
    def _setup_alert_handlers(self):
        """Configure alert handlers based on config."""
        from models import AlertSeverity
        
        severity_map = {
            "Critical": AlertSeverity.CRITICAL,
            "High": AlertSeverity.HIGH,
            "Medium": AlertSeverity.MEDIUM,
            "Low": AlertSeverity.LOW
        }
        
        if self.config.enable_console_alerts:
            severities = [severity_map[s] for s in self.config.console_severities]
            self.alert_manager.add_handler(ConsoleAlertHandler(), severities)
        
        if self.config.enable_file_alerts:
            severities = [severity_map[s] for s in self.config.file_severities]
            self.alert_manager.add_handler(FileAlertHandler(self.config.alert_file_path), severities)
        
        if self.config.enable_email_alerts:
            severities = [severity_map[s] for s in self.config.email_severities]
            email_handler = EmailAlertHandler(
                recipients=self.config.email_recipients,
                smtp_config={
                    "host": self.config.email_smtp_host,
                    "port": self.config.email_smtp_port,
                    "user": self.config.email_smtp_user,
                    "password": self.config.email_smtp_password
                }
            )
            self.alert_manager.add_handler(email_handler, severities)
        
        if self.config.enable_webhook_alerts:
            severities = [severity_map[s] for s in self.config.webhook_severities]
            webhook_handler = WebhookAlertHandler(
                webhook_url=self.config.webhook_url,
                headers=self.config.webhook_headers
            )
            self.alert_manager.add_handler(webhook_handler, severities)
    
    def process_event(self, event: EPCISEvent):
        """Process a single event and handle alerts."""
        alerts = self.processor.process_event(event)
        if alerts:
            self.alert_manager.send_alerts(alerts)
        return alerts
    
    def process_events(self, events: List[EPCISEvent]):
        """Process multiple events."""
        alerts = self.processor.process_events(events)
        if alerts:
            self.alert_manager.send_alerts(alerts)
        return alerts
    
    def generate_report(self, output_file: str = None):
        """Generate monitoring report."""
        if output_file is None:
            output_file = self.config.report_output_path
        return self.dashboard.generate_report(output_file)
    
    def show_dashboard(self):
        """Display dashboard."""
        self.dashboard.print_dashboard()


def main():
    """Main entry point."""
    # Helper to remove timezones from DataFrames before writing to Excel
    def make_naive(df):
        if df.empty:
            return df
        for col in df.columns:
            # Convert to datetime series if not already, then remove timezone
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.tz_localize(None)
            elif df[col].dtype == 'object':
                # Try to convert object columns that might contain datetimes
                try:
                    # ISO format is standard for our data
                    converted = pd.to_datetime(df[col], errors='coerce', format='ISO8601')
                    if not converted.isna().all() and converted.dt.tz is not None:
                        df[col] = converted.dt.tz_localize(None)
                except:
                    # Fallback for non-standard formats, but quiet warnings
                    try:
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            converted = pd.to_datetime(df[col], errors='coerce')
                            if not converted.isna().all() and converted.dt.tz is not None:
                                df[col] = converted.dt.tz_localize(None)
                    except:
                        pass
        return df

    parser = argparse.ArgumentParser(
        description="Monitor EPCIS events for damaged status misuse"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (JSON)"
    )
    parser.add_argument(
        "--events",
        type=str,
        help="Path to JSON file containing EPCIS events (overrides config)"
    )
    parser.add_argument(
        "--event",
        type=str,
        help="Single EPCIS event as JSON string"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate and display report (overrides config)"
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Display dashboard (overrides config)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for report"
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Fetch events from iD Cloud API instead of file (overrides config)"
    )
    parser.add_argument(
        "--hours",
        type=int,
        help="Number of hours to look back when querying API (default: from config)"
    )
    parser.add_argument(
        "--location",
        type=str,
        help="Location URN to filter events (e.g., urn:epc:id:sgln:0012345.11111.0)"
    )
    parser.add_argument(
        "--damaged-only",
        action="store_true",
        help="Only fetch events with damaged disposition (overrides config)"
    )
    parser.add_argument(
        "--max-events",
        type=int,
        help="Maximum number of events to fetch from API"
    )
    parser.add_argument(
        "--save-events",
        type=str,
        help="Save fetched events to JSON file (e.g., events_fetched.json) (overrides config)"
    )
    parser.add_argument(
        "--shipment-metrics",
        action="store_true",
        help="Calculate and display metrics for damaged items in shipments by store"
    )
    parser.add_argument(
        "--export-metrics",
        type=str,
        help="Export shipment metrics to JSON file (e.g., shipment_metrics.json)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Debug: Show which config file was loaded
    if args.config:
        print(f"Loaded configuration from: {args.config}")
    elif os.path.exists("config.json"):
        print("Loaded configuration from: config.json")
    else:
        print("Using default configuration (no config.json found)")
    
    # Initialize variables for data tracking
    shipment_metrics_data = None
    
    # Initialize location mapper (if API token is available)
    location_mapper = None
    if config.api_token and config.api_token.strip():
        try:
            print("Initializing location mapper...")
            location_mapper = LocationMapper(
                base_url=config.api_base_url,
                api_token=config.api_token
            )
            location_mapper.initialize()
            org_name = location_mapper.get_organization_name()
            if org_name:
                print(f"✅ Organization: {org_name}")
            print(f"✅ Loaded {len(location_mapper.location_to_store)} location mappings")
        except Exception as e:
            print(f"⚠️  Warning: Could not initialize location mapper: {e}")
            location_mapper = None
    
    # Initialize monitoring system
    system = MonitoringSystem(config, location_mapper=location_mapper)
    
    # Determine execution mode: use args if provided, otherwise use config
    # Check if flags were explicitly provided in command line
    provided_flags = set(sys.argv[1:])  # Get all provided arguments
    
    use_api = args.api if "--api" in provided_flags else config.use_api
    damaged_only = args.damaged_only if "--damaged-only" in provided_flags else config.damaged_only
    events_file = args.events if args.events else config.events_file
    save_events_file = args.save_events if args.save_events else config.save_events_file
    show_dashboard = args.dashboard if "--dashboard" in provided_flags else config.show_dashboard
    generate_report = args.report if "--report" in provided_flags else config.generate_report
    report_output = args.output if args.output else config.report_output_file
    
    # Fetch events from API if configured
    if use_api:
        if not config.api_token or config.api_token.strip() == "":
            print("\n❌ Error: API token not configured.")
            print("   Please set 'api_token' in config.json or use --config to specify a config file.")
            print(f"   Current api_token value: '{config.api_token}'")
            sys.exit(1)
        
        print("Fetching events from iD Cloud API...")
        api_client = IDCloudAPIClient(
            base_url=config.api_base_url,
            api_token=config.api_token,
            timeout=config.api_timeout
        )
        
        hours_back = args.hours if args.hours is not None else config.query_hours_back
        location = args.location if args.location else config.query_location
        
        try:
            if damaged_only:
                print(f"Fetching damaged events from last {hours_back} hours...")
                from_time = datetime.utcnow() - timedelta(hours=hours_back)
                events = api_client.fetch_all_damaged_events(
                    location=location,
                    from_time=from_time,
                    max_events=args.max_events if args.max_events is not None else config.query_max_events
                )
            else:
                print(f"Fetching recent events from last {hours_back} hours...")
                events = api_client.fetch_recent_events(
                    hours=hours_back,
                    location=location
                )
            
            print(f"Fetched {len(events)} events from API")
            
            # Save events to file if configured
            if save_events_file:
                print(f"Saving {len(events)} events to {save_events_file}...")
                events_data = [serialize_event_to_dict(event) for event in events]
                with open(save_events_file, "w") as f:
                    json.dump(events_data, f, indent=2, default=str)
                print(f"✅ Events saved to {save_events_file}")
            
            system.process_events(events)
            print(f"Processed {len(events)} events, generated {len(system.processor.alerts)} alerts")
            
        except Exception as e:
            print(f"Error fetching events from API: {e}")
            sys.exit(1)
    
    # Process events from file if configured
    elif events_file:
        with open(events_file, "r") as f:
            events_data = json.load(f)
            events = [EPCISEventParser.parse_from_dict(e) for e in events_data]
            system.process_events(events)
            print(f"Processed {len(events)} events, generated {len(system.processor.alerts)} alerts")
    
    elif args.event:
        event = EPCISEventParser.parse_from_json(args.event)
        alerts = system.process_event(event)
        print(f"Processed event, generated {len(alerts)} alerts")
    
    # Generate report if configured
    if generate_report:
        output_file = report_output if report_output else config.report_output_path
        report = system.generate_report(output_file)
        print(f"\nReport generated: {output_file}")
        print(report)
    
    # Calculate shipment metrics if requested
    calculate_metrics = args.shipment_metrics if "--shipment-metrics" in provided_flags else getattr(config, "calculate_shipment_metrics", False)
    
    if calculate_metrics:
        if not config.api_token or config.api_token.strip() == "":
            print("\n❌ Error: API token required for shipment metrics.")
            print("   Please set 'api_token' in config.json")
            sys.exit(1)
        
        print("\n" + "=" * 80)
        print("CALCULATING SHIPMENT METRICS")
        print("=" * 80)
        
        api_client = IDCloudAPIClient(
            base_url=config.api_base_url,
            api_token=config.api_token,
            timeout=config.api_timeout
        )
        
        try:
            shipment_metrics_data = fetch_and_calculate_metrics(api_client)
            print_metrics_report(shipment_metrics_data)
            
            # Export if requested
            export_file = args.export_metrics
            if export_file:
                output_path = export_metrics_to_json(shipment_metrics_data, export_file)
                print(f"✅ Metrics exported to: {output_path}")
            elif getattr(config, "export_shipment_metrics", False):
                output_file = getattr(config, "shipment_metrics_output_file", "shipment_metrics.json")
                output_path = export_metrics_to_json(shipment_metrics_data, output_file)
                print(f"✅ Metrics exported to: {output_path}")
        
        except Exception as e:
            print(f"❌ Error calculating shipment metrics: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # Show dashboard if configured
    if show_dashboard:
        system.show_dashboard()

    # --- Consolidated Excel Export ---
    if config.generate_excel_report:
        print("\n" + "=" * 80)
        print("GENERATING CONSOLIDATED EXCEL REPORT")
        print("=" * 80)
        
        excel_path = config.excel_report_path
        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                # 0. Execution Summary (Always visible)
                summary_data = {
                    "Metric": [
                        "Generation Time",
                        "API Base URL",
                        "Query Lookback (hours)",
                        "Report Lookback (months)",
                        "Total Alerts Detected",
                        "Consolidated Status"
                    ],
                    "Value": [
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        config.api_base_url,
                        config.query_hours_back,
                        config.stock_report_months,
                        len(system.processor.alerts),
                        "Success"
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name="Execution Summary", index=False)
                print("✅ Exported 'Execution Summary'")

                # 1. Alerts Sheet
                alerts_df = make_naive(system.dashboard.get_alerts_dataframe())
                if not alerts_df.empty:
                    alerts_df.to_excel(writer, sheet_name="Detected Misuses", index=False)
                    print(f"✅ Exported {len(alerts_df)} alerts to 'Detected Misuses'")
                
                # 2. Location Rankings Sheet
                try:
                    rankings_df = make_naive(system.dashboard.get_rankings_dataframe())
                    if not rankings_df.empty:
                        rankings_df.to_excel(writer, sheet_name="Store Rankings", index=False)
                        print("✅ Exported store rankings to 'Store Rankings'")
                    else:
                        print("ℹ️ No store rankings to export (no alerts detected).")
                except Exception as e:
                    print(f"⚠️ Warning: Could not export store rankings: {e}")
                
                # 3. Shipment Metrics Sheet (if calculated)
                if shipment_metrics_data:
                    metrics_df = make_naive(get_metrics_dataframe(shipment_metrics_data, location_mapper=location_mapper))
                    if not metrics_df.empty:
                        metrics_df.to_excel(writer, sheet_name="Shipment Metrics", index=False)
                        print("✅ Exported shipment metrics to 'Shipment Metrics'")
                
                # 4. Stock Disposition Report (History)
                print("⏳ Fetching historical stock disposition data (this may take a while)...")
                try:
                    stock_history_dfs = run_stock_disposition_report(config, location_mapper=location_mapper)
                    if stock_history_dfs:
                        for sheet_name, df in stock_history_dfs.items():
                            # Limit sheet name length for Excel (max 31 chars)
                            safe_sheet_name = f"Stock_{sheet_name}"[:31]
                            make_naive(df).to_excel(writer, sheet_name=safe_sheet_name, index=False)
                            print(f"✅ Exported historical data to '{safe_sheet_name}'")
                    else:
                        print("ℹ️ No historical stock data found to export.")
                except Exception as e:
                    print(f"⚠️ Warning: Could not include stock history in Excel: {e}")

            print(f"\n📊 Consolidated Excel report generated: {excel_path}")
            print("=" * 80 + "\n")
        except Exception as e:
            print(f"❌ Error generating Excel report: {e}")


if __name__ == "__main__":
    main()


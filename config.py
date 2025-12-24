"""
Configuration settings for the monitoring system.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class MonitoringConfig:
    """Configuration for the damaged status monitoring system."""
    
    # Alert thresholds
    high_volume_threshold_multiplier: float = 2.0
    high_volume_window_hours: int = 24
    consecutive_count_threshold: int = 2
    immediate_damaged_threshold_minutes: int = 5
    stock_mutation_timeout_minutes: int = 30
    
    # Alert handlers
    enable_console_alerts: bool = True
    enable_file_alerts: bool = True
    alert_file_path: str = "alerts.jsonl"
    
    # Email configuration (optional)
    enable_email_alerts: bool = False
    email_recipients: List[str] = field(default_factory=list)
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    email_smtp_password: str = ""
    
    # Webhook configuration (optional)
    enable_webhook_alerts: bool = False
    webhook_url: str = ""
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    
    # Severity filters for handlers
    console_severities: List[str] = field(default_factory=lambda: ["Critical", "High", "Medium", "Low"])
    file_severities: List[str] = field(default_factory=lambda: ["Critical", "High", "Medium", "Low"])
    email_severities: List[str] = field(default_factory=lambda: ["Critical", "High"])
    webhook_severities: List[str] = field(default_factory=lambda: ["Critical", "High"])
    
    # Sublocation configuration
    sellable_sublocations: List[str] = field(default_factory=lambda: [
        "Sales Floor", "Front", "Back Room", "Stock Room"
    ])
    
    # Shipment types
    return_damaged_shipment_types: List[str] = field(default_factory=lambda: [
        "Return Damaged", "Damaged Return", "DC Return"
    ])
    
    # Reporting
    report_output_path: str = "monitoring_report.json"
    dashboard_refresh_interval_seconds: int = 60
    
    # API configuration
    api_base_url: str = "https://api.nedapretail.com"  # EU production, or "https://api.nedapretail.us" for US
    api_token: str = ""  # Bearer token for authentication
    api_timeout: int = 30
    api_delay_between_requests: float = 0.5  # Delay to avoid rate limiting
    
    # Query configuration
    query_hours_back: int = 24  # Default hours to look back when querying events
    query_max_events: Optional[int] = None  # Maximum events to fetch (None for all)
    query_location: Optional[str] = None  # Filter by location URN (optional)
    
    # Execution configuration
    use_api: bool = False  # Fetch events from API instead of file
    damaged_only: bool = False  # Only fetch events with damaged disposition
    events_file: Optional[str] = None  # Path to JSON file containing EPCIS events to process
    save_events_file: Optional[str] = None  # Path to save fetched events (if None, don't save)
    show_dashboard: bool = True  # Display dashboard after processing
    generate_report: bool = False  # Generate report after processing
    report_output_file: Optional[str] = None  # Output file for report (if None, use report_output_path)
    
    # Unified Excel Export
    generate_excel_report: bool = True  # Generate a consolidated Excel report
    excel_report_path: str = "consolidated_monitoring_report.xlsx"
    
    # Shipment metrics configuration
    calculate_shipment_metrics: bool = False  # Calculate metrics for damaged items in shipments
    export_shipment_metrics: bool = False  # Export shipment metrics to file
    shipment_metrics_output_file: str = "shipment_metrics.json"  # Output file for shipment metrics

    # Damaged stock report configuration
    stock_report_months: int = 2  # Number of months to look back for the stock report
    stock_report_dispositions: List[str] = field(default_factory=lambda: ["urn:epcglobal:cbv:disp:damaged"])  # Dispositions to include
    stock_report_biz_steps: Optional[Dict[str, List[str]]] = None  # Optional custom bizSteps per disposition
    
    # Store filtering for stock report
    stock_report_store_limit: Optional[int] = None  # Maximum number of stores to process (e.g., 10)
    stock_report_store_codes: Optional[List[str]] = None  # Specific store codes to include (e.g., ["STORE001", "STORE002"])
    stock_report_store_locations: Optional[List[str]] = None  # Specific store location IDs to include


def load_config(config_file: str = None) -> MonitoringConfig:
    """Load configuration from file or return defaults."""
    import json
    import os
    
    # If no config file specified, try to find config.json in current directory
    if not config_file:
        if os.path.exists("config.json"):
            config_file = "config.json"
    
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                data = json.load(f)
                
                # Filter out keys that are not defined in the dataclass
                # (to allow informational fields starting with _ in JSON)
                import inspect
                valid_keys = {f.name for f in inspect.signature(MonitoringConfig).parameters.values()}
                filtered_data = {k: v for k, v in data.items() if k in valid_keys}
                
                return MonitoringConfig(**filtered_data)
        except Exception as e:
            print(f"\n⚠️  Warning: Could not load config from {config_file}")
            print(f"   Error: {e}")
            print("   Using default configuration values.\n")
            return MonitoringConfig()
    
    return MonitoringConfig()


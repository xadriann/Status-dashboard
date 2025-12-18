# EPC Disposition Misuse Monitoring System

A comprehensive monitoring system to detect misuse of the "Damaged" status in retail EPCIS (Electronic Product Code Information Services) events.

## Overview

This system monitors EPCIS events and detects 11 different patterns of misuse related to damaged item status, including workflow violations, inventory accuracy issues, process compliance problems, and stock mutation errors.

## Features

### Detection Rules

1. **Damaged Items in Regular Shipments** - Alerts when damaged items are added to regular shipments instead of designated return workflows
2. **Persistent Damaged Status Through Receiving** - Detects items received with damaged status that wasn't cleared
3. **Damaged Status Overwritten** - Identifies when damaged status is replaced by non-persistent statuses
4. **Damaged Items Not Observed in Counts** - Flags damaged items not found during consecutive inventory counts
5. **High Volume of Damaged Assignments** - Detects unusual spikes in damaged status assignments
6. **Damaged Items Sold at POS** - Critical alert when damaged items are sold through point-of-sale
7. **Immediate Damaged After Programming** - Identifies patterns of items marked damaged immediately after tag programming
8. **Damaged Items in Wrong Sublocation** - Alerts when damaged items appear in sellable areas
9. **Sold Items Returned as Damaged** - Detects incorrect return processing of sold items
10. **Damaged Without Stock Mutation** - Flags damaged assignments without corresponding stock adjustments
11. **Double Stock Deduction** - Critical alert for items both marked damaged and sold

### Alert System

- **Multiple Alert Handlers**: Console, file, email, and webhook support
- **Severity Levels**: Critical, High, Medium, Low
- **Configurable Routing**: Route alerts by severity to different handlers

### Dashboard & Reporting

- Real-time alert summaries
- Store-level metrics
- Rule performance tracking
- Location rankings
- Comprehensive JSON reports
- **Damaged Stock Reports**: Historical analysis of damaged assignments by week/month
- **Shipment Metrics**: Analysis of damaged items included in shipments by store

## Installation

1. Clone or download this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure API access (see Configuration section below)

## Usage

### Basic Usage

**The system is now fully configurable via `config.json`. Simply run:**

```bash
python3 main.py
```

**All execution options are configured in `config.json`:**

```json
{
  "use_api": true,                    // Fetch from API or use file
  "damaged_only": true,               // Only damaged events
  "events_file": null,                // File to process (if not using API)
  "save_events_file": "events_fetched.json",  // Save fetched events
  "show_dashboard": true,             // Show dashboard after processing
  "generate_report": false,           // Generate report
  "report_output_file": null          // Report file (null = use default)
}
```

**Command-line flags can still override config values:**

```bash
# Override config: fetch from API even if config says use file
python main.py --api

# Override config: process specific file
python main.py --events custom_events.json

# Override config: show dashboard
python main.py --dashboard

# Override config: generate report
python main.py --report --output custom_report.json

# Override config: shipment metrics
python main.py --shipment-metrics --export-metrics metrics.json
```

### Stock Disposition Report

This script generates an Excel report with historical counts of items assigned to specific dispositions (e.g., damaged) per week/store.

```bash
python generate_damaged_stock_report.py
```

**Configuration for Stock Report (`config.json`):**

```json
{
  "stock_report_months": 2,              // Months to look back
  "stock_report_dispositions": [         // Dispositions to analyze
    "urn:epcglobal:cbv:disp:damaged"
  ],
  "stock_report_biz_steps": null         // Optional custom bizSteps override
}
```

### Configuration

Create a `config.json` file (or copy `config.example.json`) to customize settings:

```json
{
  "api_base_url": "https://api.nedapretail.com",
  "api_token": "YOUR_API_TOKEN_HERE",
  "api_timeout": 30,
  "query_hours_back": 24,
  "query_location": null,
  
  "use_api": true,
  "damaged_only": true,
  "events_file": null,
  "save_events_file": "events_fetched.json",
  "show_dashboard": true,
  "generate_report": false,
  "report_output_file": null,
  
  "calculate_shipment_metrics": true,
  "export_shipment_metrics": true,
  "shipment_metrics_output_file": "shipment_metrics.json",
  
  "stock_report_months": 2,
  "stock_report_dispositions": ["urn:epcglobal:cbv:disp:damaged"],
  
  "enable_console_alerts": true,
  "enable_file_alerts": true,
  "alert_file_path": "alerts.jsonl",
  
  "high_volume_threshold_multiplier": 2.0,
  "consecutive_count_threshold": 2
}
```

**Important**: To use the API integration, you need:
1. An iD Cloud API token (Bearer token)
2. Set `api_token` in your config file
3. Choose the correct `api_base_url`:
   - `https://api.nedapretail.com` for EU production
   - `https://api.nedapretail.us` for US production

### EPCIS Event Format

Events from iD Cloud API follow the EPCIS standard format:

```json
{
  "id": "evt-001",
  "type": "object_event",
  "action": "ADD",
  "event_time": "2024-01-15T10:30:00Z",
  "event_time_zone_offset": "+00:00",
  "disposition": "urn:epcglobal:cbv:disp:damaged",
  "biz_step": "urn:epcglobal:cbv:bizstep:inspecting",
  "biz_location": "urn:epc:id:sgln:0012345.11111.0",
  "read_point": "urn:epc:id:sgln:0012345.11111.400",
  "epc_list": [
    "urn:epc:id:sgtin:123456.789012.3456789"
  ],
  "biz_transaction_list": [],
  "source_list": [],
  "destination_list": []
}
```

See `example_epcis_events.json` for more examples.

### Event Types (EPCIS)

- `object_event` - Object-level events
- `aggregation_event` - Aggregation events
- `transaction_event` - Transaction events
- `transformation_event` - Transformation events

### Business Steps

- `urn:epcglobal:cbv:bizstep:inspecting` - Inspection (can mark as damaged)
- `urn:epcglobal:cbv:bizstep:shipping` - Shipping
- `urn:epcglobal:cbv:bizstep:receiving` - Receiving
- `urn:epcglobal:cbv:bizstep:retail_selling` - Retail sale
- `urn:epcglobal:cbv:bizstep:commissioning` - Tag programming
- `urn:epcglobal:cbv:bizstep:stocking` - Moving to sales floor
- `urn:epcglobal:cbv:bizstep:storing` - Moving to stockroom

### Disposition Statuses (EPCIS URNs)

- `urn:epcglobal:cbv:disp:damaged` - Item is damaged
- `urn:epcglobal:cbv:disp:sellable_accessible` - Available for sale
- `urn:epcglobal:cbv:disp:sellable_not_accessible` - Available but not accessible
- `urn:epcglobal:cbv:disp:retail_sold` - Sold in retail store
- `http://nedapretail.com/disp/online_sold` - Sold online
- `urn:epcglobal:cbv:disp:in_transit` - Item in transit
- `urn:epcglobal:cbv:disp:active` - Active/commissioned

## Architecture 

```
models.py          - Data models (EPCISEvent, Alert, etc.)
detectors.py       - Detection rules (11 misuse patterns)
processor.py       - Event processing engine
api_client.py      - iD Cloud API client for querying events
shipment_metrics.py- Metrics for damaged items in shipments
generate_damaged_stock_report.py - Historical stock disposition report
alerter.py         - Alert handling and routing
dashboard.py       - Metrics and reporting
config.py          - Configuration management
main.py            - Main entry point
```

## API Integration

The system includes a full API client for iD Cloud's EPCIS query endpoint (`/epcis/v3/query`). The client supports:

- **Query Parameters**: Filter by disposition, biz_step, location, time range, EPC, etc.
- **Cursors**: Automatic pagination for large result sets
- **Rate Limiting**: Configurable delays between requests
- **Error Handling**: Robust error handling and retry logic

### Shipment Metrics Query

You can query items with "Damaged" disposition in "Shipping" business step to find misuse in shipments:

- **Endpoint**: `/epcis/v3/query`
- **Params**: `EQ_bizStep=urn:epcglobal:cbv:bizstep:shipping`, `EQ_disposition=urn:epcglobal:cbv:disp:damaged`

This is automatically handled by the `--shipment-metrics` flag.

### API Client Usage

You can also use the API client programmatically:

```python
from api_client import IDCloudAPIClient
from datetime import datetime, timedelta

client = IDCloudAPIClient(
    base_url="https://api.nedapretail.com",
    api_token="your_token_here"
)

# Query damaged events
events = client.fetch_all_damaged_events(
    location="urn:epc:id:sgln:0012345.11111.0",
    from_time=datetime.utcnow() - timedelta(hours=24)
)

# Query by business step
response = client.query_events_by_biz_step(
    biz_step="urn:epcglobal:cbv:bizstep:inspecting",
    from_time=datetime.utcnow() - timedelta(hours=24)
)
```

For more details on query parameters, see the [iD Cloud API documentation](documentation/Querying%20events.pdf).

## Example Workflow

1. **Event Ingestion**: EPCIS events are received from your retail system
2. **Processing**: Events are processed through the monitoring engine
3. **Detection**: Each event is evaluated against all 11 detection rules
4. **Alerting**: Alerts are generated and routed to configured handlers
5. **Reporting**: Dashboard and reports provide insights into misuse patterns

## Customization

### Adding New Detection Rules

1. Create a new class inheriting from `MisuseDetector` in `detectors.py`
2. Implement the `detect()` method
3. Add the detector to `get_all_detectors()` function

### Custom Alert Handlers

1. Create a new class inheriting from `AlertHandler` in `alerter.py`
2. Implement the `handle()` method
3. Register the handler in `MonitoringSystem._setup_alert_handlers()`

## Monitoring Recommendations

- Set up real-time event streaming for immediate detection
- Configure email/webhook alerts for critical issues
- Review dashboard daily for store-level anomalies
- Generate weekly reports for trend analysis
- Track rule performance to identify systemic issues

## License

This system is provided as-is for monitoring EPCIS events and detecting damaged status misuse patterns.


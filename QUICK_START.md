# Quick Start Guide

## Running the System

### 1. Setup Configuration

1. Get your API token from [iD Cloud Developer Portal](https://developer.nedapretail.com/)
2. Copy `config.example.json` to `config.json`
3. Configure `config.json` with your settings:

```json
{
  "api_token": "YOUR_API_TOKEN_HERE",
  "use_api": true,
  "damaged_only": true,
  "save_events_file": "events_fetched.json",
  "show_dashboard": true,
  "generate_report": false,
  "calculate_shipment_metrics": true,
  "stock_report_months": 2
}
```

### 2. Run the Monitoring System

**Simply execute (all settings from config.json):**

```bash
python main.py
```

The system will:
- Fetch events from API (if `use_api: true`)
- Process events for misuse detection
- Save events to file (if `save_events_file` is set)
- Show dashboard (if `show_dashboard: true`)
- Generate report (if `generate_report: true`)

### 3. Override with Command-Line Flags (Optional)

You can still override config values with flags:

```bash
# Override: use API even if config says use file
python main.py --api

# Override: process specific file
python main.py --events custom_events.json

# Override: show dashboard
python main.py --dashboard

# Override: generate report
python main.py --report --output custom_report.json

# Override: shipment metrics
python main.py --shipment-metrics --export-metrics metrics.json
```

### 4. Generate Damaged Stock Report (Excel)

This generates an Excel report with historical counts of damaged assignments.

```bash
python generate_damaged_stock_report.py
```

### 5. Test with Example Events

```bash
python test_example.py
```

This will process sample events and demonstrate all detection rules.

## Detection Rules Summary

| Rule ID | Rule Name | Severity | What It Detects |
|---------|-----------|----------|-----------------|
| 1 | Damaged Items in Regular Shipments | High | Damaged items added to non-return shipments |
| 2 | Persistent Damaged Through Receiving | Medium | Items received with damaged status not cleared |
| 3 | Damaged Status Overwritten | High | Damaged status replaced by non-persistent statuses |
| 4 | Damaged Not Observed in Counts | Medium | Damaged items missing from consecutive counts |
| 5 | High Volume of Damaged Assignments | Medium | Unusual spikes in damaged assignments |
| 6 | Damaged Items Sold at POS | Critical | Damaged items sold through point-of-sale |
| 7 | Immediate Damaged After Programming | Low | Items marked damaged immediately after programming |
| 8 | Damaged in Wrong Sublocation | Medium | Damaged items in sellable areas |
| 9 | Sold Items Returned as Damaged | High | Sold items incorrectly marked as damaged |
| 10 | Damaged Without Stock Mutation | Medium | Damaged assignment without stock adjustment |
| 11 | Double Stock Deduction | Critical | Item both damaged and sold |

## Configuration

Edit `config.py` or create a `config.json` file to customize:

- Alert thresholds
- Alert handlers (console, file, email, webhook)
- Severity filters
- Sublocation and shipment type definitions

## API Integration

The system includes a full API client for iD Cloud. See `example_api_usage.py` for examples:

```python
from api_client import IDCloudAPIClient
from datetime import datetime, timedelta

client = IDCloudAPIClient(
    base_url="https://api.nedapretail.com",
    api_token="your_token_here"
)

# Fetch damaged events
events = client.fetch_all_damaged_events(
    from_time=datetime.utcnow() - timedelta(hours=24)
)
```

## Integration

To integrate with your EPCIS event stream:

1. **API Integration**: Use `--api` flag or `IDCloudAPIClient` programmatically
2. **Event Format**: Events must match EPCIS standard (see `models.py`)
3. **Alert Routing**: Configure alert handlers in `config.py`
4. **Storage**: Add database persistence if needed (see `requirements.txt` for optional dependencies)
5. **Scheduling**: Set up cron jobs or scheduled tasks to run `--api` queries periodically

## Next Steps

1. Review the detection rules in `detectors.py` and adjust thresholds as needed
2. Configure alert handlers for your environment
3. Set up scheduled report generation
4. Monitor dashboard for store-level anomalies
5. Review and resolve alerts regularly


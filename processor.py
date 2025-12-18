"""
Event processor and monitoring engine for EPCIS events.
Based on iD Cloud API and EPCIS standard.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict
import json

from models import (
    EPCISEvent, Alert, EPCISEventType, EPCISAction, 
    DispositionURN, BusinessStep
)
from detectors import get_all_detectors, MisuseDetector


class EventProcessor:
    """Processes EPCIS events and triggers misuse detection."""
    
    def __init__(self):
        self.detectors = get_all_detectors()
        self.alerts: List[Alert] = []
        self.processed_events: List[EPCISEvent] = []
        self.context: Dict[str, Any] = defaultdict(dict)
        
        # Track EPC state history for detecting disposition changes
        self.epc_history: Dict[str, List[EPCISEvent]] = defaultdict(list)
        self.epc_current_state: Dict[str, Dict[str, Any]] = {}  # epc -> current state
    
    def process_event(self, event: EPCISEvent) -> List[Alert]:
        """Process a single EPCIS event and return any alerts generated."""
        alerts = []
        
        # Update EPC history and track state changes
        self._update_epc_history(event)
        
        # Update context for detectors
        self._update_context(event)
        
        # Run all detectors
        for detector in self.detectors:
            try:
                alert = detector.detect(event, self.context)
                if alert:
                    alerts.append(alert)
                    self.alerts.append(alert)
            except Exception as e:
                print(f"Error in detector {detector.rule_name}: {e}")
        
        # Store processed event
        self.processed_events.append(event)
        
        return alerts
    
    def process_events(self, events: List[EPCISEvent]) -> List[Alert]:
        """Process multiple events and return all alerts."""
        all_alerts = []
        for event in events:
            alerts = self.process_event(event)
            all_alerts.extend(alerts)
        return all_alerts
    
    def _update_epc_history(self, event: EPCISEvent):
        """Track EPC state history to detect disposition changes."""
        for epc in event.epc_list:
            # Store event in history
            self.epc_history[epc].append(event)
            
            # Update current state
            if event.disposition:
                self.epc_current_state[epc] = {
                    "disposition": event.disposition,
                    "location": event.get_location(),
                    "biz_step": event.biz_step,
                    "event_time": event.event_time,
                    "event_id": event.id
                }
    
    def get_previous_disposition(self, epc: str, current_event: EPCISEvent) -> Optional[str]:
        """Get the previous disposition for an EPC before the current event."""
        if epc not in self.epc_current_state:
            return None
        
        # Get the state before current event
        previous_state = self.epc_current_state.get(epc)
        if previous_state and previous_state.get("event_time") < current_event.event_time:
            return previous_state.get("disposition")
        
        return None
    
    def _update_context(self, event: EPCISEvent):
        """Update shared context for detectors."""
        # Track bulk operations (multiple EPCs in one event)
        if len(event.epc_list) > 1:
            self.context["is_bulk_operation"] = True
        else:
            self.context["is_bulk_operation"] = False
        
        # Store transaction info for sales
        if event.is_sold():
            # Extract transaction ID from biz_transaction_list
            for biz_txn in event.biz_transaction_list:
                if biz_txn.get("type") == "urn:epcglobal:cbv:btt:inv":
                    self.context["transaction_id"] = biz_txn.get("value")
                    break
        
        # Add previous disposition info to context
        primary_epc = event.get_primary_epc()
        if primary_epc:
            prev_disp = self.get_previous_disposition(primary_epc, event)
            self.context["previous_disposition"] = prev_disp
            self.context["epc"] = primary_epc
    
    def get_alerts_by_severity(self, severity: str) -> List[Alert]:
        """Get alerts filtered by severity."""
        return [a for a in self.alerts if a.severity.value == severity]
    
    def get_alerts_by_location(self, location: str) -> List[Alert]:
        """Get alerts filtered by location."""
        return [a for a in self.alerts if a.location == location]
    
    def get_alerts_by_rule(self, rule_id: int) -> List[Alert]:
        """Get alerts filtered by rule ID."""
        return [a for a in self.alerts if a.rule_id == rule_id]
    
    def get_unresolved_alerts(self) -> List[Alert]:
        """Get all unresolved alerts."""
        return [a for a in self.alerts if not a.resolved]
    
    def resolve_alert(self, alert_id: str):
        """Mark an alert as resolved."""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now()
                break


class EPCISEventParser:
    """Parses EPCIS events from iD Cloud API format."""
    
    @staticmethod
    def parse_from_dict(data: Dict[str, Any]) -> EPCISEvent:
        """Parse an EPCIS event from a dictionary (iD Cloud API format)."""
        # Parse event time
        event_time_str = data.get("event_time", "")
        if isinstance(event_time_str, str):
            event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
        else:
            event_time = datetime.now()
        
        # Parse record time if present
        record_time = None
        if data.get("record_time"):
            record_time_str = data.get("record_time")
            if isinstance(record_time_str, str):
                record_time = datetime.fromisoformat(record_time_str.replace("Z", "+00:00"))
        
        # Handle EPCs: aggregation_event uses child_epcs, object_event uses epc_list
        event_type = data.get("type", "object_event")
        epc_list = data.get("epc_list", [])
        if event_type == "aggregation_event" and "child_epcs" in data:
            # For aggregation events, use child_epcs as the EPC list
            # API structure: aggregation_event has "child_epcs" field instead of "epc_list"
            epc_list = data.get("child_epcs", [])
        
        # source_list and destination_list structure from API:
        # [{"type": "urn:epcglobal:cbv:sdt:location", "source": "http://..."}]
        # [{"type": "urn:epcglobal:cbv:sdt:location", "destination": "http://..."}]
        source_list = data.get("source_list", [])
        destination_list = data.get("destination_list", [])
        
        return EPCISEvent(
            id=data.get("id", data.get("event_id", "")),
            type=EPCISEventType(event_type),
            action=EPCISAction(data.get("action", "OBSERVE")),
            event_time=event_time,
            event_time_zone_offset=data.get("event_time_zone_offset"),
            record_time=record_time,
            disposition=data.get("disposition"),
            biz_step=data.get("biz_step"),
            biz_location=data.get("biz_location"),
            read_point=data.get("read_point"),
            epc_list=epc_list,
            quantity_list=data.get("quantity_list", []),
            biz_transaction_list=data.get("biz_transaction_list", []),
            source_list=source_list,
            destination_list=destination_list,
            error_declaration=data.get("error_declaration"),
            stored_id=data.get("stored_id"),
            event_id=data.get("event_id"),
            metadata=data.get("metadata", {})
        )
    
    @staticmethod
    def parse_from_json(json_str: str) -> EPCISEvent:
        """Parse an EPCIS event from JSON string."""
        data = json.loads(json_str)
        return EPCISEventParser.parse_from_dict(data)
    
    @staticmethod
    def parse_batch_from_json(json_str: str) -> List[EPCISEvent]:
        """Parse multiple EPCIS events from JSON array."""
        data = json.loads(json_str)
        events = []
        for item in data:
            # Handle both single events and events in "events" array
            if isinstance(item, dict) and "events" in item:
                # Response format from query API
                for event_data in item["events"]:
                    events.append(EPCISEventParser.parse_from_dict(event_data))
            elif isinstance(item, dict):
                events.append(EPCISEventParser.parse_from_dict(item))
        return events
    
    @staticmethod
    def parse_from_epcis_query_response(response: Dict[str, Any]) -> List[EPCISEvent]:
        """Parse events from EPCIS query API response."""
        events = []
        for event_data in response.get("events", []):
            events.append(EPCISEventParser.parse_from_dict(event_data))
        return events

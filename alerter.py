"""
Alerting system for misuse detection.
"""
from typing import List, Optional, Callable, Dict
from datetime import datetime
import json

from models import Alert, AlertSeverity


class AlertHandler:
    """Base class for alert handlers."""
    
    def handle(self, alert: Alert):
        """Handle a single alert. Override in subclasses."""
        raise NotImplementedError


class ConsoleAlertHandler(AlertHandler):
    """Prints alerts to console."""
    
    def handle(self, alert: Alert):
        severity_symbol = {
            AlertSeverity.CRITICAL: "🔴",
            AlertSeverity.HIGH: "🟠",
            AlertSeverity.MEDIUM: "🟡",
            AlertSeverity.LOW: "🔵"
        }.get(alert.severity, "⚪")
        
        print(f"\n{severity_symbol} ALERT [{alert.severity.value}]")
        print(f"  Rule: {alert.rule_name} (ID: {alert.rule_id})")
        print(f"  Time: {alert.timestamp}")
        print(f"  Location: {alert.location}")
        print(f"  EPC: {alert.epc}")
        print(f"  Description: {alert.description}")
        if alert.details:
            print(f"  Details: {json.dumps(alert.details, indent=4, default=str)}")
        print("-" * 60)


class FileAlertHandler(AlertHandler):
    """Writes alerts to a file."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
    
    def handle(self, alert: Alert):
        with open(self.filepath, "a") as f:
            f.write(json.dumps({
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "timestamp": alert.timestamp.isoformat(),
                "epc": alert.epc,
                "location": alert.location,
                "description": alert.description,
                "details": alert.details,
                "resolved": alert.resolved,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None
            }, indent=2, default=str) + "\n")


class EmailAlertHandler(AlertHandler):
    """Sends alerts via email (placeholder for actual implementation)."""
    
    def __init__(self, recipients: List[str], smtp_config: Optional[Dict] = None):
        self.recipients = recipients
        self.smtp_config = smtp_config or {}
        self.critical_alerts_buffer: List[Alert] = []
    
    def handle(self, alert: Alert):
        # Buffer critical alerts for batch sending
        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            self.critical_alerts_buffer.append(alert)
            if len(self.critical_alerts_buffer) >= 10:
                self._send_batch_email()
    
    def _send_batch_email(self):
        """Send batched critical alerts via email."""
        # Placeholder - implement actual email sending logic
        print(f"[EMAIL] Would send {len(self.critical_alerts_buffer)} critical alerts to {self.recipients}")
        self.critical_alerts_buffer.clear()
    
    def flush(self):
        """Flush any remaining buffered alerts."""
        if self.critical_alerts_buffer:
            self._send_batch_email()


class WebhookAlertHandler(AlertHandler):
    """Sends alerts to a webhook endpoint."""
    
    def __init__(self, webhook_url: str, headers: Optional[Dict] = None):
        self.webhook_url = webhook_url
        self.headers = headers or {}
    
    def handle(self, alert: Alert):
        # Placeholder - implement actual webhook POST
        import requests
        try:
            payload = {
                "alert_id": alert.alert_id,
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "timestamp": alert.timestamp.isoformat(),
                "location": alert.location,
                "epc": alert.epc,
                "description": alert.description,
                "details": alert.details
            }
            # Uncomment when ready to use:
            # response = requests.post(self.webhook_url, json=payload, headers=self.headers)
            # response.raise_for_status()
            print(f"[WEBHOOK] Would POST alert {alert.alert_id} to {self.webhook_url}")
        except Exception as e:
            print(f"[WEBHOOK] Error sending alert: {e}")


class AlertManager:
    """Manages alert handlers and routing."""
    
    def __init__(self):
        self.handlers: List[AlertHandler] = []
        self.severity_filters: Dict[AlertSeverity, List[AlertHandler]] = {}
    
    def add_handler(self, handler: AlertHandler, severities: Optional[List[AlertSeverity]] = None):
        """Add an alert handler, optionally filtered by severity."""
        if severities:
            for severity in severities:
                if severity not in self.severity_filters:
                    self.severity_filters[severity] = []
                self.severity_filters[severity].append(handler)
        else:
            self.handlers.append(handler)
    
    def send_alert(self, alert: Alert):
        """Send an alert through all appropriate handlers."""
        # Send to severity-specific handlers
        if alert.severity in self.severity_filters:
            for handler in self.severity_filters[alert.severity]:
                try:
                    handler.handle(alert)
                except Exception as e:
                    print(f"Error in alert handler: {e}")
        
        # Send to general handlers
        for handler in self.handlers:
            try:
                handler.handle(alert)
            except Exception as e:
                print(f"Error in alert handler: {e}")
    
    def send_alerts(self, alerts: List[Alert]):
        """Send multiple alerts."""
        for alert in alerts:
            self.send_alert(alert)


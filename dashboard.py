"""
Dashboard and reporting module for damaged status monitoring.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
import json

from models import Alert, StoreMetrics, AlertSeverity
from processor import EventProcessor


class Dashboard:
    """Generates metrics and reports for damaged status monitoring."""
    
    def __init__(self, processor: EventProcessor):
        self.processor = processor
    
    def get_store_metrics(self, location: str, date: Optional[datetime] = None) -> StoreMetrics:
        """Get metrics for a specific store."""
        if date is None:
            date = datetime.now()
        
        alerts = self.processor.get_alerts_by_location(location)
        date_alerts = [a for a in alerts if a.timestamp.date() == date.date()]
        
        damaged_assignments = len([a for a in date_alerts if a.rule_id == 5])
        damaged_in_shipments = len([a for a in date_alerts if a.rule_id == 1])
        damaged_sold = len([a for a in date_alerts if a.rule_id == 6])
        damaged_not_observed = len([a for a in date_alerts if a.rule_id == 4])
        
        # Calculate historical average (simplified - would need historical data)
        historical_avg = damaged_assignments * 0.8  # Placeholder
        
        anomalies = []
        if damaged_assignments > historical_avg * 2:
            anomalies.append("High volume of damaged assignments")
        if damaged_sold > 0:
            anomalies.append("Damaged items sold at POS")
        if damaged_in_shipments > 0:
            anomalies.append("Damaged items in regular shipments")
        
        return StoreMetrics(
            location=location,
            date=date,
            damaged_assignments=damaged_assignments,
            damaged_in_shipments=damaged_in_shipments,
            damaged_sold=damaged_sold,
            damaged_not_observed=damaged_not_observed,
            historical_avg_damaged=historical_avg,
            anomalies=anomalies
        )
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of all alerts."""
        alerts = self.processor.alerts
        unresolved = self.processor.get_unresolved_alerts()
        
        by_severity = defaultdict(int)
        by_rule = defaultdict(int)
        by_location = defaultdict(int)
        
        for alert in unresolved:
            by_severity[alert.severity.value] += 1
            by_rule[alert.rule_id] += 1
            by_location[alert.location] += 1
        
        return {
            "total_alerts": len(alerts),
            "unresolved_alerts": len(unresolved),
            "by_severity": dict(by_severity),
            "by_rule": dict(by_rule),
            "by_location": dict(by_location),
            "recent_alerts": [
                {
                    "alert_id": a.alert_id,
                    "rule_name": a.rule_name,
                    "severity": a.severity.value,
                    "location": a.location,
                    "timestamp": a.timestamp.isoformat()
                }
                for a in sorted(unresolved, key=lambda x: x.timestamp, reverse=True)[:10]
            ]
        }
    
    def get_rule_performance(self) -> Dict[int, Dict[str, Any]]:
        """Get performance metrics for each detection rule."""
        rule_stats = {}
        
        for rule_id in range(1, 12):
            rule_alerts = self.processor.get_alerts_by_rule(rule_id)
            unresolved = [a for a in rule_alerts if not a.resolved]
            
            rule_stats[rule_id] = {
                "total_detections": len(rule_alerts),
                "unresolved": len(unresolved),
                "resolved": len(rule_alerts) - len(unresolved),
                "resolution_rate": (len(rule_alerts) - len(unresolved)) / len(rule_alerts) if rule_alerts else 0
            }
        
        return rule_stats
    
    def get_location_rankings(self, metric: str = "total_alerts") -> List[Dict[str, Any]]:
        """Get location rankings by various metrics."""
        location_data = defaultdict(lambda: {
            "total_alerts": 0,
            "critical_alerts": 0,
            "high_alerts": 0,
            "medium_alerts": 0,
            "low_alerts": 0
        })
        
        for alert in self.processor.get_unresolved_alerts():
            loc_data = location_data[alert.location]
            loc_data["total_alerts"] += 1
            if alert.severity == AlertSeverity.CRITICAL:
                loc_data["critical_alerts"] += 1
            elif alert.severity == AlertSeverity.HIGH:
                loc_data["high_alerts"] += 1
            elif alert.severity == AlertSeverity.MEDIUM:
                loc_data["medium_alerts"] += 1
            else:
                loc_data["low_alerts"] += 1
        
        rankings = [
            {"location": loc, **data}
            for loc, data in location_data.items()
        ]
        
        return sorted(rankings, key=lambda x: x.get(metric, 0), reverse=True)
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """Generate a comprehensive monitoring report."""
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": self.get_alert_summary(),
            "rule_performance": self.get_rule_performance(),
            "location_rankings": self.get_location_rankings(),
            "top_issues": [
                {
                    "rule_id": rule_id,
                    "rule_name": f"Rule {rule_id}",
                    "count": stats["unresolved"]
                }
                for rule_id, stats in self.get_rule_performance().items()
                if stats["unresolved"] > 0
            ]
        }
        
        report_json = json.dumps(report, indent=2, default=str)
        
        if output_file:
            with open(output_file, "w") as f:
                f.write(report_json)
        
        return report_json
    
    def print_dashboard(self):
        """Print a formatted dashboard to console."""
        summary = self.get_alert_summary()
        
        print("\n" + "=" * 80)
        print("DAMAGED STATUS MISUSE MONITORING DASHBOARD")
        print("=" * 80)
        print(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n📊 SUMMARY")
        print(f"  Total Alerts: {summary['total_alerts']}")
        print(f"  Unresolved: {summary['unresolved_alerts']}")
        
        print(f"\n🔴 By Severity:")
        for severity, count in summary['by_severity'].items():
            print(f"  {severity}: {count}")
        
        print(f"\n📍 Top Locations:")
        for loc_data in self.get_location_rankings()[:5]:
            print(f"  {loc_data['location']}: {loc_data['total_alerts']} alerts "
                  f"({loc_data['critical_alerts']} critical)")
        
        print(f"\n📋 Recent Alerts:")
        for alert in summary['recent_alerts'][:5]:
            print(f"  [{alert['severity']}] {alert['rule_name']} @ {alert['location']} "
                  f"({alert['timestamp']})")
        
        print("\n" + "=" * 80 + "\n")

    def get_alerts_dataframe(self) -> Any:
        """Get all alerts as a Pandas DataFrame."""
        import pandas as pd
        data = []
        for alert in self.processor.alerts:
            data.append({
                "Alert ID": alert.alert_id,
                "Rule ID": alert.rule_id,
                "Rule Name": alert.rule_name,
                "Severity": alert.severity.value,
                "Timestamp": alert.timestamp,
                "EPC": alert.epc,
                "Location": alert.location,
                "Description": alert.description,
                "Resolved": alert.resolved,
                "Resolved At": alert.resolved_at
            })
        return pd.DataFrame(data)

    def get_rankings_dataframe(self) -> Any:
        """Get location rankings as a Pandas DataFrame."""
        import pandas as pd
        rankings = self.get_location_rankings()
        return pd.DataFrame(rankings)


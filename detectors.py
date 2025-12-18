"""
Detection rules for damaged status misuse patterns.
Based on iD Cloud API and EPCIS standard.
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from collections import defaultdict

from models import (
    EPCISEvent, Alert, AlertSeverity, DispositionURN, BusinessStep
)


class MisuseDetector:
    """Base class for misuse detection rules."""
    
    def __init__(self, rule_id: int, rule_name: str, severity: AlertSeverity):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.severity = severity
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        """Detect misuse based on event and context. Override in subclasses."""
        raise NotImplementedError


class Rule1_DamagedInShipments(MisuseDetector):
    """Rule 1: Damaged items in regular shipments."""
    
    def __init__(self):
        super().__init__(1, "Damaged Items in Regular Shipments", AlertSeverity.HIGH)
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Check if event is shipping with damaged disposition
        if (event.is_shipment() and 
            event.is_damaged() and
            event.action.value == "ADD"):
            primary_epc = event.get_primary_epc()
            location = event.get_location()
            
            if primary_epc and location:
                # Check if this is a return shipment (would have specific destination)
                # Regular shipments shouldn't contain damaged items
                is_return = any(
                    dest.get("type") == "urn:epcglobal:cbv:sdt:owning_party" 
                    for dest in event.destination_list
                )
                
                if not is_return:
                    return Alert(
                        alert_id=f"R1_{event.id}",
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        severity=self.severity,
                        timestamp=event.event_time,
                        epc=primary_epc,
                        location=location,
                        description="Damaged item added to regular shipment",
                        details={
                            "biz_step": event.biz_step,
                            "disposition": event.disposition,
                            "expected": "Return shipment for damaged items"
                        },
                        event_id=event.id
                    )
        return None


class Rule2_PersistentDamagedInReceiving(MisuseDetector):
    """Rule 2: Persistent damaged status through receiving."""
    
    def __init__(self):
        super().__init__(2, "Persistent Damaged Status Through Receiving", AlertSeverity.MEDIUM)
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Check if event is receiving with damaged disposition
        if (event.is_receiving() and 
            event.is_damaged()):
            primary_epc = event.get_primary_epc()
            location = event.get_location()
            previous_disp = context.get("previous_disposition")
            
            if primary_epc and location and previous_disp:
                # If previous disposition was also damaged, it wasn't cleared
                if DispositionURN.is_damaged(previous_disp):
                    return Alert(
                        alert_id=f"R2_{event.id}",
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        severity=self.severity,
                        timestamp=event.event_time,
                        epc=primary_epc,
                        location=location,
                        description="Item received with damaged status that wasn't cleared",
                        details={
                            "previous_disposition": previous_disp,
                            "current_disposition": event.disposition,
                            "biz_step": event.biz_step
                        },
                        event_id=event.id
                    )
        return None


class Rule3_DamagedOverwritten(MisuseDetector):
    """Rule 3: Damaged status overwritten by non-persistent statuses."""
    
    def __init__(self):
        super().__init__(3, "Damaged Status Overwritten", AlertSeverity.HIGH)
        # Non-persistent statuses that shouldn't overwrite damaged
        self.non_persistent_statuses = {
            DispositionURN.SELLABLE_ACCESSIBLE.value,
            DispositionURN.SELLABLE_NOT_ACCESSIBLE.value,
            DispositionURN.ACTIVE.value
        }
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        previous_disp = context.get("previous_disposition")
        current_disp = event.get_disposition()
        
        # Check if damaged was overwritten by non-persistent status
        if (previous_disp and current_disp and
            DispositionURN.is_damaged(previous_disp) and
            current_disp in self.non_persistent_statuses):
            primary_epc = event.get_primary_epc()
            location = event.get_location()
            is_bulk = context.get("is_bulk_operation", False)
            
            if primary_epc and location:
                return Alert(
                    alert_id=f"R3_{event.id}",
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    severity=self.severity,
                    timestamp=event.event_time,
                    epc=primary_epc,
                    location=location,
                    description=f"Damaged status overwritten by {current_disp}",
                    details={
                        "previous_disposition": previous_disp,
                        "new_disposition": current_disp,
                        "is_bulk_operation": is_bulk,
                        "biz_step": event.biz_step
                    },
                    event_id=event.id
                )
        return None


class Rule4_DamagedNotObserved(MisuseDetector):
    """Rule 4: Damaged items not observed during counts."""
    
    def __init__(self, consecutive_count_threshold: int = 2):
        super().__init__(4, "Damaged Items Not Observed in Counts", AlertSeverity.MEDIUM)
        self.consecutive_count_threshold = consecutive_count_threshold
        self.damaged_items: Dict[str, Dict[str, Any]] = {}  # epc -> tracking info
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        primary_epc = event.get_primary_epc()
        if not primary_epc:
            return None
        
        location = event.get_location()
        
        # Track when items are marked as damaged
        if event.is_damaged() and event.action.value == "ADD":
            self.damaged_items[primary_epc] = {
                "damaged_since": event.event_time,
                "location": location,
                "count_not_observed": 0
            }
        
        # Check during inventory counts (OBSERVE actions at same location)
        if (event.action.value == "OBSERVE" and 
            location and
            primary_epc in self.damaged_items):
            item_info = self.damaged_items[primary_epc]
            if location == item_info["location"]:
                # Item was observed, reset counter
                item_info["count_not_observed"] = 0
            else:
                # Item not observed in this count
                item_info["count_not_observed"] += 1
                
                if item_info["count_not_observed"] >= self.consecutive_count_threshold:
                    return Alert(
                        alert_id=f"R4_{event.id}",
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        severity=self.severity,
                        timestamp=event.event_time,
                        epc=primary_epc,
                        location=item_info["location"],
                        description=f"Damaged item not observed for {item_info['count_not_observed']} consecutive counts",
                        details={
                            "damaged_since": item_info["damaged_since"].isoformat(),
                            "consecutive_counts_missing": item_info["count_not_observed"]
                        },
                        event_id=event.id
                    )
        
        return None


class Rule5_HighVolumeDamaged(MisuseDetector):
    """Rule 5: High volume of damaged status assignments."""
    
    def __init__(self, threshold_multiplier: float = 2.0, window_hours: int = 24):
        super().__init__(5, "High Volume of Damaged Assignments", AlertSeverity.MEDIUM)
        self.threshold_multiplier = threshold_multiplier
        self.window_hours = window_hours
        self.location_assignments: Dict[str, List[datetime]] = defaultdict(list)
        self.location_historical_avg: Dict[str, float] = {}
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Check if this is an inspection marking items as damaged
        if (event.is_inspection() and 
            event.is_damaged() and
            event.action.value == "ADD"):
            location = event.get_location()
            if not location:
                return None
            
            now = event.event_time
            
            # Clean old entries outside window
            cutoff = now - timedelta(hours=self.window_hours)
            self.location_assignments[location] = [
                ts for ts in self.location_assignments[location] if ts > cutoff
            ]
            
            # Add current assignment (count EPCs in event)
            num_damaged = len(event.epc_list)
            for _ in range(num_damaged):
                self.location_assignments[location].append(now)
            
            # Calculate current rate
            current_count = len(self.location_assignments[location])
            
            # Get or calculate historical average
            if location not in self.location_historical_avg:
                # Initialize with current count (first time)
                self.location_historical_avg[location] = current_count
                return None
            
            historical_avg = self.location_historical_avg[location]
            threshold = historical_avg * self.threshold_multiplier
            
            if current_count > threshold:
                primary_epc = event.get_primary_epc()
                return Alert(
                    alert_id=f"R5_{event.id}",
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    severity=self.severity,
                    timestamp=event.event_time,
                    epc=primary_epc or "multiple",
                    location=location,
                    description=f"Unusual spike in damaged assignments: {current_count} vs avg {historical_avg:.1f}",
                    details={
                        "current_count": current_count,
                        "historical_average": historical_avg,
                        "threshold": threshold,
                        "window_hours": self.window_hours,
                        "num_items_in_event": num_damaged
                    },
                    event_id=event.id
                )
            
            # Update historical average (moving average)
            self.location_historical_avg[location] = (
                historical_avg * 0.9 + current_count * 0.1
            )
        
        return None


class Rule6_DamagedSoldAtPOS(MisuseDetector):
    """Rule 6: Damaged items sold at POS."""
    
    def __init__(self):
        super().__init__(6, "Damaged Items Sold at POS", AlertSeverity.CRITICAL)
        self.damaged_items: set = set()  # Track EPCs with damaged status
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Track damaged items
        if event.is_damaged() and event.action.value == "ADD":
            for epc in event.epc_list:
                self.damaged_items.add(epc)
        
        # Remove if status changes away from damaged
        previous_disp = context.get("previous_disposition")
        if previous_disp and not DispositionURN.is_damaged(previous_disp):
            primary_epc = event.get_primary_epc()
            if primary_epc:
                self.damaged_items.discard(primary_epc)
        
        # Check for sales
        if event.is_sold():
            for epc in event.epc_list:
                if epc in self.damaged_items:
                    location = event.get_location()
                    return Alert(
                        alert_id=f"R6_{event.id}",
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        severity=self.severity,
                        timestamp=event.event_time,
                        epc=epc,
                        location=location or "unknown",
                        description="Damaged item sold through point-of-sale",
                        details={
                            "transaction_id": context.get("transaction_id"),
                            "biz_step": event.biz_step,
                            "disposition": event.disposition
                        },
                        event_id=event.id
                    )
        
        return None


class Rule7_ImmediateDamagedAfterProgramming(MisuseDetector):
    """Rule 7: Items immediately marked damaged after programming."""
    
    def __init__(self, time_threshold_minutes: int = 5):
        super().__init__(7, "Immediate Damaged After Programming", AlertSeverity.LOW)
        self.time_threshold = timedelta(minutes=time_threshold_minutes)
        self.programmed_items: Dict[str, datetime] = {}  # epc -> programming time
        self.recent_alerts: Dict[str, int] = defaultdict(int)  # location -> count
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Track commissioning (tag programming)
        if (event.biz_step == BusinessStep.COMMISSIONING.value and
            event.action.value == "ADD"):
            for epc in event.epc_list:
                self.programmed_items[epc] = event.event_time
        
        # Check for immediate damaged assignment
        if (event.is_inspection() and 
            event.is_damaged() and
            event.action.value == "ADD"):
            for epc in event.epc_list:
                if epc in self.programmed_items:
                    time_diff = event.event_time - self.programmed_items[epc]
                    if time_diff < self.time_threshold:
                        location = event.get_location()
                        if location:
                            self.recent_alerts[location] += 1
                            
                            # Only alert if pattern detected (multiple occurrences)
                            if self.recent_alerts[location] >= 3:
                                return Alert(
                                    alert_id=f"R7_{event.id}",
                                    rule_id=self.rule_id,
                                    rule_name=self.rule_name,
                                    severity=self.severity,
                                    timestamp=event.event_time,
                                    epc=epc,
                                    location=location,
                                    description=f"Item marked damaged {time_diff.total_seconds():.0f}s after programming",
                                    details={
                                        "time_since_programming_seconds": time_diff.total_seconds(),
                                        "pattern_count": self.recent_alerts[location]
                                    },
                                    event_id=event.id
                                )
        
        return None


class Rule8_DamagedInWrongSublocation(MisuseDetector):
    """Rule 8: Damaged items in wrong sublocation."""
    
    def __init__(self):
        super().__init__(8, "Damaged Items in Wrong Sublocation", AlertSeverity.MEDIUM)
        # These biz_steps indicate sellable areas
        self.sellable_biz_steps = {
            BusinessStep.STOCKING.value,  # Moving to sales floor
            BusinessStep.STORING.value  # In stockroom (but accessible)
        }
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Check if damaged item is in sellable area
        if (event.is_damaged() and
            event.biz_step in self.sellable_biz_steps):
            primary_epc = event.get_primary_epc()
            location = event.get_location()
            
            if primary_epc and location:
                return Alert(
                    alert_id=f"R8_{event.id}",
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    severity=self.severity,
                    timestamp=event.event_time,
                    epc=primary_epc,
                    location=location,
                    description=f"Damaged item in sellable area (biz_step: {event.biz_step})",
                    details={
                        "biz_step": event.biz_step,
                        "read_point": event.read_point,
                        "expected": "Non-sellable area"
                    },
                    event_id=event.id
                )
        return None


class Rule9_SoldItemsReturnedAsDamaged(MisuseDetector):
    """Rule 9: Sold items incorrectly returned as damaged."""
    
    def __init__(self):
        super().__init__(9, "Sold Items Returned as Damaged", AlertSeverity.HIGH)
        self.sold_items: set = set()  # Track EPCs with sold status
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Track sold items
        if event.is_sold() and event.action.value == "ADD":
            for epc in event.epc_list:
                self.sold_items.add(epc)
        
        # Check if sold item is marked as damaged
        if (event.is_inspection() and
            event.is_damaged() and
            event.action.value == "ADD"):
            for epc in event.epc_list:
                if epc in self.sold_items:
                    location = event.get_location()
                    return Alert(
                        alert_id=f"R9_{event.id}",
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        severity=self.severity,
                        timestamp=event.event_time,
                        epc=epc,
                        location=location or "unknown",
                        description="Sold item incorrectly returned as damaged without proper return processing",
                        details={
                            "previous_status": "Sold",
                            "requires_return_processing": True,
                            "biz_step": event.biz_step
                        },
                        event_id=event.id
                    )
        
        return None


class Rule10_DamagedWithoutStockMutation(MisuseDetector):
    """Rule 10: Damaged status without corresponding stock mutation."""
    
    def __init__(self):
        super().__init__(10, "Damaged Without Stock Mutation", AlertSeverity.MEDIUM)
        self.damaged_events: Dict[str, EPCISEvent] = {}  # epc -> damaged event
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Track damaged assignments
        if (event.is_inspection() and
            event.is_damaged() and
            event.action.value == "ADD"):
            for epc in event.epc_list:
                self.damaged_events[epc] = event
        
        # Check for stock mutation (DELETE action typically indicates stock removal)
        if event.action.value == "DELETE":
            for epc in event.epc_list:
                if epc in self.damaged_events:
                    # Stock mutation found, remove from tracking
                    del self.damaged_events[epc]
        
        # Check for missing stock mutations (after timeout)
        now = event.event_time
        for epc, damaged_event in list(self.damaged_events.items()):
            time_diff = now - damaged_event.event_time
            if time_diff > timedelta(minutes=30):  # 30 minute window
                location = damaged_event.get_location()
                return Alert(
                    alert_id=f"R10_{event.id}",
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    severity=self.severity,
                    timestamp=now,
                    epc=epc,
                    location=location or "unknown",
                    description="Damaged status assigned without corresponding stock adjustment",
                    details={
                        "damaged_assigned_at": damaged_event.event_time.isoformat(),
                        "time_since_assignment_minutes": time_diff.total_seconds() / 60
                    },
                    event_id=damaged_event.id
                )
        
        return None


class Rule11_DoubleStockDeduction(MisuseDetector):
    """Rule 11: Double stock deduction (damaged + sold)."""
    
    def __init__(self):
        super().__init__(11, "Double Stock Deduction", AlertSeverity.CRITICAL)
        self.recently_damaged: Dict[str, datetime] = {}  # epc -> damaged timestamp
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Track damaged assignments
        if (event.is_inspection() and
            event.is_damaged() and
            event.action.value == "ADD"):
            for epc in event.epc_list:
                self.recently_damaged[epc] = event.event_time
        
        # Check for sales of recently damaged items
        if event.is_sold():
            for epc in event.epc_list:
                if epc in self.recently_damaged:
                    damaged_time = self.recently_damaged[epc]
                    time_diff = event.event_time - damaged_time
                    
                    # Alert if sold within 24 hours of being marked damaged
                    if time_diff < timedelta(hours=24):
                        location = event.get_location()
                        return Alert(
                            alert_id=f"R11_{event.id}",
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            severity=self.severity,
                            timestamp=event.event_time,
                            epc=epc,
                            location=location or "unknown",
                            description="Item both marked damaged and sold, causing double stock deduction",
                            details={
                                "damaged_at": damaged_time.isoformat(),
                                "sold_at": event.event_time.isoformat(),
                                "time_between_hours": time_diff.total_seconds() / 3600,
                                "biz_step": event.biz_step
                            },
                            event_id=event.id
                        )
        
        # Clean old entries
        cutoff = event.event_time - timedelta(days=1)
        self.recently_damaged = {
            epc: ts for epc, ts in self.recently_damaged.items() if ts > cutoff
        }
        
        return None


def get_all_detectors() -> List[MisuseDetector]:
    """Get all configured misuse detectors."""
    return [
        Rule1_DamagedInShipments(),
        Rule2_PersistentDamagedInReceiving(),
        Rule3_DamagedOverwritten(),
        Rule4_DamagedNotObserved(),
        Rule5_HighVolumeDamaged(),
        Rule6_DamagedSoldAtPOS(),
        Rule7_ImmediateDamagedAfterProgramming(),
        Rule8_DamagedInWrongSublocation(),
        Rule9_SoldItemsReturnedAsDamaged(),
        Rule10_DamagedWithoutStockMutation(),
        Rule11_DoubleStockDeduction()
    ]

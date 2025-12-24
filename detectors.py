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
from config import load_config


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
    """Rule 3: Status Released - Detects when a status is released (sellable_accessible, sellable_not_accessible, or active) 
    in a biz_step associated with the dispositions configured in stock_report_dispositions."""
    
    def __init__(self):
        super().__init__(3, "Status Released", AlertSeverity.HIGH)
        
        # Load configuration to get selected dispositions
        config = load_config()
        selected_dispositions = config.stock_report_dispositions or []
        
        # Get biz_steps from custom config or default mapping
        # Import the mapping from generate_damaged_stock_report
        try:
            from generate_damaged_stock_report import DISPOSITION_TO_BIZSTEP
        except ImportError:
            # Fallback mapping if import fails
            DISPOSITION_TO_BIZSTEP = {}
        
        # Collect all biz_steps from selected dispositions
        self.target_biz_steps = set()
        config_biz_steps = config.stock_report_biz_steps or {}
        
        for disposition in selected_dispositions:
            # Use custom biz_steps from config if available, otherwise use default mapping
            if disposition in config_biz_steps:
                biz_steps = config_biz_steps[disposition]
            else:
                biz_steps = DISPOSITION_TO_BIZSTEP.get(disposition, [])
            
            if biz_steps:
                if isinstance(biz_steps, list):
                    self.target_biz_steps.update(biz_steps)
                else:
                    self.target_biz_steps.add(biz_steps)
        
        # Statuses that indicate a status release
        self.released_statuses = {
            DispositionURN.SELLABLE_ACCESSIBLE.value,
            DispositionURN.SELLABLE_NOT_ACCESSIBLE.value,
            DispositionURN.ACTIVE.value
        }
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # If no target biz_steps configured, skip detection
        if not self.target_biz_steps:
            return None
        
        # Check if event has a biz_step that matches our target biz_steps
        event_biz_step = event.biz_step
        if not event_biz_step or event_biz_step not in self.target_biz_steps:
            return None
        
        # Check if the event disposition is a "released" status
        current_disp = event.get_disposition()
        if not current_disp or current_disp not in self.released_statuses:
            return None
        
        # This is a status release event
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
                description=f"Status released: {current_disp} in biz_step {event_biz_step}",
                details={
                    "disposition": current_disp,
                    "biz_step": event_biz_step,
                    "is_bulk_operation": is_bulk,
                    "action": event.action.value if event.action else None
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


class Rule7_DispositionIncorrectInSalesFloor(MisuseDetector):
    """Rule 7: Detects dispositions that should not be in sales_floor sublocations."""
    
    def __init__(self):
        super().__init__(7, "Incorrect Disposition in Sales Floor", AlertSeverity.MEDIUM)
        
        # Dispositions that should NOT be in sales_floor
        self.incorrect_dispositions_sales_floor = {
            DispositionURN.SELLABLE_NOT_ACCESSIBLE.value,
            DispositionURN.RETAIL_SOLD.value,
            DispositionURN.IN_TRANSIT.value,
            DispositionURN.NON_SELLABLE_OTHER.value,
            DispositionURN.DAMAGED.value,
            "http://nedapretail.com/disp/online_sold",
            "http://nedapretail.com/disp/in_progress",
            "http://nedapretail.com/disp/container_closed",
            "http://nedapretail.com/disp/received_order",
            "http://nedapretail.com/disp/retail_reserved",
            "http://nedapretail.com/disp/retail_reserved_for_peak",
            "http://nedapretail.com/disp/lent",
            "http://nedapretail.com/disp/faulty",
            "http://nedapretail.com/disp/missing_article",
            "http://nedapretail.com/disp/customized",
            "http://nedapretail.com/disp/hemming"
        }
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Check if event has a disposition that's incorrect for sales_floor
        current_disp = event.get_disposition()
        if not current_disp or current_disp not in self.incorrect_dispositions_sales_floor:
            return None
        
        # Get location and check if it's a sales_floor sublocation
        location = event.get_location()
        if not location:
            return None
        
        location_mapper = context.get("location_mapper")
        if not location_mapper:
            return None
        
        # Get sublocation type from location_mapper
        store_info = location_mapper.get_store_info(location)
        sublocation_type = store_info.get("sublocation_type")
        
        # Check if this is a sales_floor sublocation
        if sublocation_type != "sales_floor":
            return None
        
        # This is an incorrect disposition in sales_floor
        primary_epc = event.get_primary_epc()
        if primary_epc:
            return Alert(
                alert_id=f"R7_{event.id}",
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                severity=self.severity,
                timestamp=event.event_time,
                epc=primary_epc,
                location=location,
                description=f"Disposition {current_disp} should not be in sales_floor sublocation",
                details={
                    "disposition": current_disp,
                    "sublocation_type": sublocation_type,
                    "sublocation_name": store_info.get("sublocation_name"),
                    "store_name": store_info.get("store_name"),
                    "biz_step": event.biz_step
                },
                event_id=event.id
            )
        return None


class Rule8_DispositionIncorrectInStockroom(MisuseDetector):
    """Rule 8: Detects dispositions that should not be in stockroom sublocations."""
    
    def __init__(self):
        super().__init__(8, "Incorrect Disposition in Stockroom", AlertSeverity.MEDIUM)
        
        # Dispositions that should NOT be in stockroom
        self.incorrect_dispositions_stockroom = {
            DispositionURN.SELLABLE_ACCESSIBLE.value,
            DispositionURN.RETAIL_SOLD.value,
            "http://nedapretail.com/disp/on_display",
            "http://nedapretail.com/disp/in_showcase"
        }
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Check if event has a disposition that's incorrect for stockroom
        current_disp = event.get_disposition()
        if not current_disp or current_disp not in self.incorrect_dispositions_stockroom:
            return None
        
        # Get location and check if it's a stockroom sublocation
        location = event.get_location()
        if not location:
            return None
        
        location_mapper = context.get("location_mapper")
        if not location_mapper:
            return None
        
        # Get sublocation type from location_mapper
        store_info = location_mapper.get_store_info(location)
        sublocation_type = store_info.get("sublocation_type")
        
        # Check if this is a stockroom sublocation
        if sublocation_type != "stockroom":
            return None
        
        # This is an incorrect disposition in stockroom
        primary_epc = event.get_primary_epc()
        if primary_epc:
            return Alert(
                alert_id=f"R8_{event.id}",
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                severity=self.severity,
                timestamp=event.event_time,
                epc=primary_epc,
                location=location,
                description=f"Disposition {current_disp} should not be in stockroom sublocation",
                details={
                    "disposition": current_disp,
                    "sublocation_type": sublocation_type,
                    "sublocation_name": store_info.get("sublocation_name"),
                    "store_name": store_info.get("store_name"),
                    "biz_step": event.biz_step
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


class Rule12_RetailSoldInCycleCounting(MisuseDetector):
    """Rule 12: Retail sold items detected during cycle counting."""
    
    def __init__(self):
        super().__init__(12, "Retail Sold in Cycle Counting", AlertSeverity.HIGH)
        self.cycle_counting_biz_step = "urn:epcglobal:cbv:bizstep:cycle_counting"
        self.retail_sold_disposition = DispositionURN.RETAIL_SOLD.value
    
    def detect(self, event: EPCISEvent, context: Dict[str, Any]) -> Optional[Alert]:
        # Check if event has retail_sold disposition and cycle_counting biz_step
        current_disp = event.get_disposition()
        event_biz_step = event.biz_step
        
        if (current_disp == self.retail_sold_disposition and 
            event_biz_step == self.cycle_counting_biz_step):
            primary_epc = event.get_primary_epc()
            location = event.get_location()
            
            if primary_epc and location:
                return Alert(
                    alert_id=f"R12_{event.id}",
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    severity=self.severity,
                    timestamp=event.event_time,
                    epc=primary_epc,
                    location=location,
                    description="Retail sold item detected during cycle counting",
                    details={
                        "disposition": current_disp,
                        "biz_step": event_biz_step,
                        "action": event.action.value if event.action else None
                    },
                    event_id=event.id
                )
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
        Rule7_DispositionIncorrectInSalesFloor(),
        Rule8_DispositionIncorrectInStockroom(),
        Rule9_SoldItemsReturnedAsDamaged(),
        Rule10_DamagedWithoutStockMutation(),
        Rule11_DoubleStockDeduction(),
        Rule12_RetailSoldInCycleCounting()
    ]

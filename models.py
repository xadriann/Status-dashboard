"""
Data models for EPCIS events and damaged status monitoring.
Based on iD Cloud API and EPCIS standard.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class DispositionURN(str, Enum):
    """EPCIS disposition URNs according to CBV standard."""
    # Standard CBV dispositions
    DAMAGED = "urn:epcglobal:cbv:disp:damaged"
    SELLABLE_ACCESSIBLE = "urn:epcglobal:cbv:disp:sellable_accessible"
    SELLABLE_NOT_ACCESSIBLE = "urn:epcglobal:cbv:disp:sellable_not_accessible"
    IN_TRANSIT = "urn:epcglobal:cbv:disp:in_transit"
    RETAIL_SOLD = "urn:epcglobal:cbv:disp:retail_sold"
    ACTIVE = "urn:epcglobal:cbv:disp:active"
    NON_SELLABLE_OTHER = "urn:epcglobal:cbv:disp:non_sellable_other"
    UNKNOWN = "urn:epcglobal:cbv:disp:unknown"
    
    # Nedap Retail specific dispositions
    ONLINE_SOLD = "http://nedapretail.com/disp/online_sold"
    FAULTY = "http://nedapretail.com/disp/faulty"
    MISSING_ARTICLE = "http://nedapretail.com/disp/missing_article"
    CUSTOMIZED = "http://nedapretail.com/disp/customized"
    HEMMING = "http://nedapretail.com/disp/hemming"
    ON_DISPLAY = "http://nedapretail.com/disp/on_display"
    RECEIVED_ORDER = "http://nedapretail.com/disp/received_order"
    LENT = "http://nedapretail.com/disp/lent"
    RETAIL_RESERVED = "http://nedapretail.com/disp/retail_reserved"
    
    @classmethod
    def from_string(cls, value: str) -> Optional['DispositionURN']:
        """Convert string to DispositionURN if valid."""
        for disposition in cls:
            if disposition.value == value:
                return disposition
        return None
    
    @classmethod
    def is_damaged(cls, value: str) -> bool:
        """Check if disposition represents damaged status."""
        return value == cls.DAMAGED.value
    
    @classmethod
    def is_sellable(cls, value: str) -> bool:
        """Check if disposition represents sellable status."""
        return value in [
            cls.SELLABLE_ACCESSIBLE.value,
            cls.SELLABLE_NOT_ACCESSIBLE.value
        ]
    
    @classmethod
    def is_sold(cls, value: str) -> bool:
        """Check if disposition represents sold status."""
        return value in [
            cls.RETAIL_SOLD.value,
            cls.ONLINE_SOLD.value
        ]


class EPCISEventType(str, Enum):
    """EPCIS event types according to standard."""
    OBJECT_EVENT = "object_event"
    AGGREGATION_EVENT = "aggregation_event"
    TRANSACTION_EVENT = "transaction_event"
    TRANSFORMATION_EVENT = "transformation_event"


class EPCISAction(str, Enum):
    """EPCIS action types."""
    ADD = "ADD"
    OBSERVE = "OBSERVE"
    DELETE = "DELETE"


class BusinessStep(str, Enum):
    """Common business steps from CBV standard."""
    COMMISSIONING = "urn:epcglobal:cbv:bizstep:commissioning"
    INSPECTING = "urn:epcglobal:cbv:bizstep:inspecting"
    SHIPPING = "urn:epcglobal:cbv:bizstep:shipping"
    RECEIVING = "urn:epcglobal:cbv:bizstep:receiving"
    RETAIL_SELLING = "urn:epcglobal:cbv:bizstep:retail_selling"
    STORING = "urn:epcglobal:cbv:bizstep:storing"
    STOCKING = "urn:epcglobal:cbv:bizstep:stocking"
    HOLDING = "urn:epcglobal:cbv:bizstep:holding"
    
    # Nedap Retail specific
    CUSTOMIZING = "http://nedapretail.com/bizstep/customizing"
    DISPLAYING = "http://nedapretail.com/bizstep/displaying"
    LENDING = "http://nedapretail.com/bizstep/lending"
    RETAIL_RESERVING = "http://nedapretail.com/bizstep/retail_reserving"
    VOID_RETAIL_SELLING_TRANSACTION = "http://nedapretail.com/bizstep/void_retail_selling_transaction"
    VOID_RETAIL_SELLING_LINE = "http://nedapretail.com/bizstep/void_retail_selling_line"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class EPCISEvent:
    """Represents an EPCIS event according to iD Cloud API structure."""
    # Core EPCIS fields
    id: str  # EPCIS event message identifier
    type: EPCISEventType  # object_event, aggregation_event, etc.
    action: EPCISAction  # ADD, OBSERVE, DELETE
    event_time: datetime  # When the event occurred
    event_time_zone_offset: Optional[str] = None  # Timezone offset (e.g., "+01:00")
    record_time: Optional[datetime] = None  # When event was recorded
    
    # Business context
    disposition: Optional[str] = None  # Disposition URN
    biz_step: Optional[str] = None  # Business step URN
    biz_location: Optional[str] = None  # Business location URN
    read_point: Optional[str] = None  # Read point URN
    
    # EPCs and quantities
    epc_list: List[str] = field(default_factory=list)  # List of EPCs
    quantity_list: List[Dict[str, Any]] = field(default_factory=list)  # Quantities
    
    # Business transactions
    biz_transaction_list: List[Dict[str, Any]] = field(default_factory=list)
    source_list: List[Dict[str, Any]] = field(default_factory=list)
    destination_list: List[Dict[str, Any]] = field(default_factory=list)
    
    # Error declaration
    error_declaration: Optional[Dict[str, Any]] = None
    
    # Additional metadata
    stored_id: Optional[str] = None  # Database ID
    event_id: Optional[str] = None  # Alternative event ID
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_primary_epc(self) -> Optional[str]:
        """Get the primary EPC from the event."""
        return self.epc_list[0] if self.epc_list else None
    
    def get_all_epcs(self) -> List[str]:
        """Get all EPCs from the event (handles both epc_list and child_epcs for aggregation events)."""
        return self.epc_list
    
    def get_location(self) -> Optional[str]:
        """Extract location from biz_location URN."""
        return self.biz_location
    
    def get_disposition(self) -> Optional[str]:
        """Get disposition URN."""
        return self.disposition
    
    def is_damaged(self) -> bool:
        """Check if event has damaged disposition."""
        return DispositionURN.is_damaged(self.disposition) if self.disposition else False
    
    def is_sold(self) -> bool:
        """Check if event represents a sale."""
        return (self.biz_step == BusinessStep.RETAIL_SELLING.value or
                (self.disposition and DispositionURN.is_sold(self.disposition)))
    
    def is_inspection(self) -> bool:
        """Check if event is an inspection (which can mark items as damaged)."""
        return self.biz_step == BusinessStep.INSPECTING.value
    
    def is_shipment(self) -> bool:
        """Check if event is related to shipping."""
        return self.biz_step == BusinessStep.SHIPPING.value
    
    def is_receiving(self) -> bool:
        """Check if event is related to receiving."""
        return self.biz_step == BusinessStep.RECEIVING.value


@dataclass
class Alert:
    """Represents a misuse detection alert."""
    alert_id: str
    rule_id: int
    rule_name: str
    severity: AlertSeverity
    timestamp: datetime
    epc: str
    location: str
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    event_id: Optional[str] = None  # Reference to EPCIS event


@dataclass
class DamagedItem:
    """Tracks a damaged item and its lifecycle."""
    epc: str
    location: str
    damaged_since: datetime
    last_observed: datetime
    count_not_observed: int = 0
    sublocation: Optional[str] = None
    shipment_id: Optional[str] = None
    event_id: Optional[str] = None  # EPCIS event that marked it damaged
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StoreMetrics:
    """Metrics for a specific store."""
    location: str
    date: datetime
    damaged_assignments: int = 0
    damaged_in_shipments: int = 0
    damaged_sold: int = 0
    damaged_not_observed: int = 0
    historical_avg_damaged: float = 0.0
    anomalies: List[str] = field(default_factory=list)

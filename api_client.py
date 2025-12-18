"""
API client for iD Cloud EPCIS query endpoint.
Based on iD Cloud API documentation for querying events.
"""
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time

from models import EPCISEvent
from processor import EPCISEventParser


class IDCloudAPIClient:
    """Client for querying EPCIS events from iD Cloud API."""
    
    def __init__(
        self,
        base_url: str = "https://api.nedapretail.com",
        api_token: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize the API client.
        
        Args:
            base_url: Base URL for iD Cloud API (EU or US)
            api_token: Bearer token for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.timeout = timeout
        self.session = requests.Session()
        
        if self.api_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json'
            })
    
    def query_epcis_events(
        self,
        parameters: Optional[List[Dict[str, Any]]] = None,
        use_cursor: bool = False,
        from_cursor: Optional[str] = None,
        max_event_count: Optional[int] = None,
        event_count_limit: Optional[int] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query EPCIS events using the /epcis/v3/query endpoint.
        
        Args:
            parameters: List of query parameters (e.g., [{"name": "EQ_disposition", "value": "urn:epcglobal:cbv:disp:damaged"}])
            use_cursor: Whether to use cursors for pagination
            from_cursor: Cursor value from previous response
            max_event_count: Maximum number of events to return (mutually exclusive with event_count_limit)
            event_count_limit: Limit number of events (mutually exclusive with max_event_count)
            order_by: Field to sort by (eventTime, recordTime, or quantity)
            order_direction: Sort direction (ASC or DESC)
        
        Returns:
            Response dictionary with 'events' and 'has_more'/'next_cursor' if using cursors
        """
        url = f"{self.base_url}/epcis/v3/query"
        
        query_body = {}
        
        if parameters:
            query_body["parameters"] = parameters
        
        if use_cursor:
            query_body["use_cursor"] = True
            if from_cursor:
                query_body["from_cursor"] = from_cursor
        
        if max_event_count is not None:
            query_body["maxEventCount"] = max_event_count
        
        if event_count_limit is not None:
            query_body["eventCountLimit"] = event_count_limit
        
        if order_by:
            query_body["orderBy"] = order_by
        
        if order_direction:
            query_body["orderDirection"] = order_direction.upper()
        
        try:
            response = self.session.post(url, json=query_body, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {e}")
    
    def query_damaged_events(
        self,
        location: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        use_cursor: bool = True,
        from_cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query events with damaged disposition.
        
        Args:
            location: Business location URN to filter by
            from_time: Start time for event filtering
            to_time: End time for event filtering
            use_cursor: Whether to use cursors
            from_cursor: Cursor from previous response
        
        Returns:
            Response dictionary with events
        """
        parameters = [
            {
                "name": "EQ_disposition",
                "value": "urn:epcglobal:cbv:disp:damaged"
            }
        ]
        
        if location:
            parameters.append({
                "name": "EQ_bizLocation",
                "value": location
            })
        
        if from_time:
            parameters.append({
                "name": "GE_eventTime",
                "value": from_time.isoformat()
            })
        
        if to_time:
            parameters.append({
                "name": "LT_eventTime",
                "value": to_time.isoformat()
            })
        
        return self.query_epcis_events(
            parameters=parameters,
            use_cursor=use_cursor,
            from_cursor=from_cursor
        )
    
    def query_events_by_biz_step(
        self,
        biz_step: str,
        location: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        use_cursor: bool = True,
        from_cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query events by business step.
        
        Args:
            biz_step: Business step URN (e.g., "urn:epcglobal:cbv:bizstep:inspecting")
            location: Business location URN to filter by
            from_time: Start time for event filtering
            to_time: End time for event filtering
            use_cursor: Whether to use cursors
            from_cursor: Cursor from previous response
        
        Returns:
            Response dictionary with events
        """
        parameters = [
            {
                "name": "EQ_bizStep",
                "value": biz_step
            }
        ]
        
        if location:
            parameters.append({
                "name": "EQ_bizLocation",
                "value": location
            })
        
        if from_time:
            parameters.append({
                "name": "GE_eventTime",
                "value": from_time.isoformat()
            })
        
        if to_time:
            parameters.append({
                "name": "LT_eventTime",
                "value": to_time.isoformat()
            })
        
        return self.query_epcis_events(
            parameters=parameters,
            use_cursor=use_cursor,
            from_cursor=from_cursor
        )
    
    def query_events_by_epc(
        self,
        epc: str,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        use_cursor: bool = True,
        from_cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query events for a specific EPC.
        
        Args:
            epc: EPC URI (pure identity or pattern)
            from_time: Start time for event filtering
            to_time: End time for event filtering
            use_cursor: Whether to use cursors
            from_cursor: Cursor from previous response
        
        Returns:
            Response dictionary with events
        """
        parameters = [
            {
                "name": "MATCH_epc",
                "value": epc
            }
        ]
        
        if from_time:
            parameters.append({
                "name": "GE_eventTime",
                "value": from_time.isoformat()
            })
        
        if to_time:
            parameters.append({
                "name": "LT_eventTime",
                "value": to_time.isoformat()
            })
        
        return self.query_epcis_events(
            parameters=parameters,
            use_cursor=use_cursor,
            from_cursor=from_cursor
        )
    
    def fetch_all_events(
        self,
        parameters: Optional[List[Dict[str, Any]]] = None,
        max_events: Optional[int] = None,
        delay_between_requests: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Fetch all events matching criteria using cursors.
        
        Args:
            parameters: Query parameters
            max_events: Maximum number of events to fetch (None for all)
            delay_between_requests: Delay in seconds between API requests
        
        Returns:
            List of all event dictionaries
        """
        all_events = []
        cursor = None
        use_cursor = True
        
        while True:
            try:
                response = self.query_epcis_events(
                    parameters=parameters,
                    use_cursor=use_cursor,
                    from_cursor=cursor
                )
                
                events = response.get("events", [])
                all_events.extend(events)
                
                # Check if we've reached the limit
                if max_events and len(all_events) >= max_events:
                    return all_events[:max_events]
                
                # Check if there are more events
                has_more = response.get("has_more", False)
                cursor = response.get("next_cursor")
                
                if not has_more or not cursor:
                    break
                
                # Delay to avoid rate limiting
                if delay_between_requests > 0:
                    time.sleep(delay_between_requests)
                    
            except Exception as e:
                print(f"Error fetching events: {e}")
                break
        
        return all_events
    
    def fetch_all_damaged_events(
        self,
        location: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        max_events: Optional[int] = None
    ) -> List[EPCISEvent]:
        """
        Fetch all damaged events and parse them into EPCISEvent objects.
        
        Args:
            location: Business location URN
            from_time: Start time
            to_time: End time
            max_events: Maximum number of events
        
        Returns:
            List of parsed EPCISEvent objects
        """
        parameters = [
            {
                "name": "EQ_disposition",
                "value": "urn:epcglobal:cbv:disp:damaged"
            }
        ]
        
        if location:
            parameters.append({
                "name": "EQ_bizLocation",
                "value": location
            })
        
        if from_time:
            parameters.append({
                "name": "GE_eventTime",
                "value": from_time.isoformat()
            })
        
        if to_time:
            parameters.append({
                "name": "LT_eventTime",
                "value": to_time.isoformat()
            })
        
        event_dicts = self.fetch_all_events(
            parameters=parameters,
            max_events=max_events
        )
        
        # Parse events
        parsed_events = []
        for event_dict in event_dicts:
            try:
                event = EPCISEventParser.parse_from_dict(event_dict)
                parsed_events.append(event)
            except Exception as e:
                print(f"Error parsing event {event_dict.get('id', 'unknown')}: {e}")
        
        return parsed_events
    
    def query_damaged_in_shipments(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        use_cursor: bool = True,
        from_cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query events with damaged disposition in shipping biz_step.
        This identifies damaged items being shipped from stores.
        
        Args:
            from_time: Start time for event filtering
            to_time: End time for event filtering
            use_cursor: Whether to use cursors
            from_cursor: Cursor from previous response
        
        Returns:
            Response dictionary with events
        """
        parameters = [
            {
                "name": "EQ_bizStep",
                "value": "urn:epcglobal:cbv:bizstep:shipping"
            },
            {
                "name": "EQ_disposition",
                "value": "urn:epcglobal:cbv:disp:damaged"
            }
        ]
        
        if from_time:
            parameters.append({
                "name": "GE_eventTime",
                "value": from_time.isoformat()
            })
        
        if to_time:
            parameters.append({
                "name": "LT_eventTime",
                "value": to_time.isoformat()
            })
        
        return self.query_epcis_events(
            parameters=parameters,
            use_cursor=use_cursor,
            from_cursor=from_cursor
        )
    
    def fetch_all_damaged_in_shipments(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        max_events: Optional[int] = None
    ) -> List[EPCISEvent]:
        """
        Fetch all events with damaged disposition in shipping and parse them.
        
        Args:
            from_time: Start time
            to_time: End time
            max_events: Maximum number of events
        
        Returns:
            List of parsed EPCISEvent objects
        """
        parameters = [
            {
                "name": "EQ_bizStep",
                "value": "urn:epcglobal:cbv:bizstep:shipping"
            },
            {
                "name": "EQ_disposition",
                "value": "urn:epcglobal:cbv:disp:damaged"
            }
        ]
        
        if from_time:
            parameters.append({
                "name": "GE_eventTime",
                "value": from_time.isoformat()
            })
        
        if to_time:
            parameters.append({
                "name": "LT_eventTime",
                "value": to_time.isoformat()
            })
        
        event_dicts = self.fetch_all_events(
            parameters=parameters,
            max_events=max_events
        )
        
        # Parse events
        parsed_events = []
        for event_dict in event_dicts:
            try:
                event = EPCISEventParser.parse_from_dict(event_dict)
                parsed_events.append(event)
            except Exception as e:
                print(f"Error parsing event {event_dict.get('id', 'unknown')}: {e}")
        
        return parsed_events
    
    def fetch_recent_events(
        self,
        hours: int = 24,
        location: Optional[str] = None,
        disposition: Optional[str] = None
    ) -> List[EPCISEvent]:
        """
        Fetch recent events from the last N hours.
        
        Args:
            hours: Number of hours to look back
            location: Business location URN to filter by
            disposition: Disposition URN to filter by
        
        Returns:
            List of parsed EPCISEvent objects
        """
        from_time = datetime.utcnow() - timedelta(hours=hours)
        
        parameters = [
            {
                "name": "GE_eventTime",
                "value": from_time.isoformat()
            }
        ]
        
        if location:
            parameters.append({
                "name": "EQ_bizLocation",
                "value": location
            })
        
        if disposition:
            parameters.append({
                "name": "EQ_disposition",
                "value": disposition
            })
        
        event_dicts = self.fetch_all_events(parameters=parameters)
        
        # Parse events
        parsed_events = []
        for event_dict in event_dicts:
            try:
                event = EPCISEventParser.parse_from_dict(event_dict)
                parsed_events.append(event)
            except Exception as e:
                print(f"Error parsing event {event_dict.get('id', 'unknown')}: {e}")
        
        return parsed_events


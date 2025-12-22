"""
Location mapping module for translating location IDs to store and sublocation names.
"""
import requests
from typing import Dict, Optional, Tuple
from collections import defaultdict


class LocationMapper:
    """Maps location IDs to store names and sublocation names."""
    
    def __init__(self, base_url: str, api_token: str):
        """
        Initialize the location mapper.
        
        Args:
            base_url: Base URL for iD Cloud API
            api_token: Bearer token for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.location_to_store: Dict[str, Dict[str, str]] = {}  # location_id -> {store_name, sublocation_name, store_location}
        self.organization_name: Optional[str] = None
        self._initialized = False
    
    def _get_headers(self):
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def initialize(self):
        """Fetch and cache store and sublocation information from API."""
        if self._initialized:
            return
        
        try:
            # Get organization name
            org_url = f"{self.base_url}/organization/v1/retrieve"
            org_response = requests.get(org_url, headers=self._get_headers())
            org_response.raise_for_status()
            org_data = org_response.json()
            self.organization_name = org_data.get("own", {}).get("name")
            
            # Get all stores
            stores_url = f"{self.base_url}/organization/v2/list_stores"
            params = {
                "fields[]": ["location", "name", "store_code", "store_type", "sublocations"]
            }
            stores_response = requests.get(stores_url, headers=self._get_headers(), params=params)
            stores_response.raise_for_status()
            stores_data = stores_response.json()
            
            # Handle both list and dict responses
            stores = stores_data if isinstance(stores_data, list) else stores_data.get("stores", [])
            
            # Build mapping
            for store in stores:
                store_name = store.get("name", "Unknown Store")
                store_location = store.get("location")
                
                # Map main store location
                if store_location:
                    self.location_to_store[store_location] = {
                        "store_name": store_name,
                        "sublocation_name": None,  # Main store location, no sublocation
                        "store_location": store_location
                    }
                
                # Map sublocations
                sublocations = store.get("sublocations", [])
                for sublocation in sublocations:
                    sublocation_location = sublocation.get("location")
                    sublocation_name = sublocation.get("name", "Unknown Sublocation")
                    
                    if sublocation_location:
                        self.location_to_store[sublocation_location] = {
                            "store_name": store_name,
                            "sublocation_name": sublocation_name,
                            "store_location": store_location or sublocation_location
                        }
            
            self._initialized = True
            
        except Exception as e:
            print(f"⚠️  Warning: Could not initialize location mapper: {e}")
            print("   Location IDs will be shown without store names.")
            self._initialized = False
    
    def get_store_info(self, location_id: str) -> Dict[str, Optional[str]]:
        """
        Get store information for a location ID.
        
        Args:
            location_id: Location URN (e.g., "http://nedapretail.com/loc/store-123")
        
        Returns:
            Dictionary with store_name, sublocation_name, and store_location
        """
        if not self._initialized:
            self.initialize()
        
        info = self.location_to_store.get(location_id, {})
        return {
            "store_name": info.get("store_name"),
            "sublocation_name": info.get("sublocation_name"),
            "store_location": info.get("store_location", location_id)
        }
    
    def get_display_name(self, location_id: str) -> str:
        """
        Get a human-readable display name for a location.
        
        Args:
            location_id: Location URN
        
        Returns:
            Formatted string like "Store Name (Sublocation Name) [location_id]"
        """
        info = self.get_store_info(location_id)
        store_name = info.get("store_name")
        sublocation_name = info.get("sublocation_name")
        
        parts = []
        if store_name:
            parts.append(store_name)
        if sublocation_name:
            parts.append(f"({sublocation_name})")
        
        if parts:
            return f"{' '.join(parts)} [{location_id}]"
        else:
            return location_id
    
    def get_short_display_name(self, location_id: str) -> str:
        """
        Get a shorter display name without the location ID.
        
        Args:
            location_id: Location URN
        
        Returns:
            Formatted string like "Store Name (Sublocation Name)"
        """
        info = self.get_store_info(location_id)
        store_name = info.get("store_name")
        sublocation_name = info.get("sublocation_name")
        
        parts = []
        if store_name:
            parts.append(store_name)
        if sublocation_name:
            parts.append(f"({sublocation_name})")
        
        if parts:
            return " ".join(parts)
        else:
            return location_id
    
    def get_organization_name(self) -> Optional[str]:
        """Get the organization name."""
        if not self._initialized:
            self.initialize()
        return self.organization_name


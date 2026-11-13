"""
Running List manager module.
Loads customer and farm master data from 'Running List.xlsx'
and provides zone-filtered lists for Chilaw, Puttalam, and Middle Zone.
"""

import os
import logging
from typing import List, Dict, Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_EXCEL_FILENAME = "Running List.xlsx"


class RunningListManager:
    """
    Manages customer and farm name mappings by Zone from Running List.xlsx.
    """

    def __init__(self, excel_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.excel_path = excel_path or os.path.join(base_dir, DEFAULT_EXCEL_FILENAME)
        self.df = None
        self._load_data()

    def _load_data(self):
        """Loads and cleans data from Running List.xlsx."""
        if not os.path.exists(self.excel_path):
            logger.warning(f"Running List file not found at {self.excel_path}")
            self.df = pd.DataFrame(columns=["Customer Name", "Farm Name with Code", "Zone"])
            return

        try:
            raw_df = pd.read_excel(self.excel_path)
            # Find matching column names flexibly
            col_map = {}
            for col in raw_df.columns:
                c_clean = str(col).strip().lower()
                if "customer" in c_clean:
                    col_map[col] = "Customer Name"
                elif "farm" in c_clean:
                    col_map[col] = "Farm Name with Code"
                elif "zone" in c_clean:
                    col_map[col] = "Zone"

            df = raw_df.rename(columns=col_map)
            for req in ["Customer Name", "Farm Name with Code", "Zone"]:
                if req not in df.columns:
                    df[req] = ""

            # Clean and strip strings
            df = df.dropna(subset=["Customer Name", "Farm Name with Code"])
            df["Customer Name"] = df["Customer Name"].astype(str).str.strip()
            df["Farm Name with Code"] = df["Farm Name with Code"].astype(str).str.strip()
            df["Zone"] = df["Zone"].astype(str).str.strip()

            self.df = df
            logger.info(f"Loaded {len(self.df)} records from {self.excel_path}")
        except Exception as e:
            logger.error(f"Error loading {self.excel_path}: {e}")
            self.df = pd.DataFrame(columns=["Customer Name", "Farm Name with Code", "Zone"])

    def get_all_zones(self) -> List[str]:
        """Returns list of distinct zones found in the file."""
        if self.df is None or self.df.empty:
            return ["Chilaw", "Puttalam", "Middle Zone"]
        zones = [z for z in self.df["Zone"].unique() if z]
        return sorted(zones)

    def get_items_for_zone(self, zone: str) -> List[Dict[str, str]]:
        """
        Returns all customer-farm items for a given zone.
        If zone is empty or 'all', returns all.
        """
        if self.df is None or self.df.empty:
            return []

        zone_str = (zone or "").strip().lower()
        if not zone_str or zone_str == "all":
            sub_df = self.df
        else:
            sub_df = self.df[self.df["Zone"].str.lower() == zone_str]

        items = []
        for _, row in sub_df.iterrows():
            items.append({
                "customer": row["Customer Name"],
                "farm": row["Farm Name with Code"],
                "zone": row["Zone"],
            })
        return items

    def get_customers_for_zone(self, zone: str) -> List[str]:
        """Returns sorted unique customer names for a zone."""
        items = self.get_items_for_zone(zone)
        customers = sorted(list(set(item["customer"] for item in items if item["customer"])))
        return customers

    def get_farms_for_zone(self, zone: str, customer: Optional[str] = None) -> List[str]:
        """Returns sorted unique farm names with code for a zone (optionally filtered by customer)."""
        items = self.get_items_for_zone(zone)
        if customer:
            c_clean = customer.strip().lower()
            items = [it for it in items if it["customer"].lower() == c_clean]
        farms = sorted(list(set(item["farm"] for item in items if item["farm"])))
        return farms

    def get_zone_data_bundle(self, zone: str) -> Dict[str, Any]:
        """
        Bundles customers, farms, and item pairs for frontend consumption.
        """
        items = self.get_items_for_zone(zone)
        customers = sorted(list(set(it["customer"] for it in items if it["customer"])))
        farms = sorted(list(set(it["farm"] for it in items if it["farm"])))
        return {
            "zone": zone,
            "total_items": len(items),
            "customers": customers,
            "farms": farms,
            "items": items,
        }


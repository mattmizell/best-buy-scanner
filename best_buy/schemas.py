"""
Pydantic schemas for Best Buy Scanner API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal


# ==================== Product Schemas ====================

class ProductBase(BaseModel):
    upc: str
    name: str
    department: Optional[str] = None
    current_vendor: Optional[str] = None
    current_cost: Optional[float] = None
    retail_price: Optional[float] = None
    pack_size: int = 1


class ProductCreate(ProductBase):
    pass


class ProductResponse(ProductBase):
    id: int
    on_hand: int = 0
    last_synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Supplier Schemas ====================

class SupplierBase(BaseModel):
    code: str
    name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    min_order_amount: Optional[float] = None
    order_lead_days: int = 2
    delivery_days: Optional[str] = None
    feed_type: Optional[str] = "manual"


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    id: int
    is_active: bool = True
    last_feed_sync: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Supplier Price Schemas ====================

class SupplierPriceBase(BaseModel):
    upc: str
    supplier_id: int
    unit_cost: float
    case_cost: Optional[float] = None
    case_pack: int = 1
    effective_date: datetime
    expires_at: Optional[datetime] = None
    price_type: str = "list"
    promo_name: Optional[str] = None
    in_stock: bool = True


class SupplierPriceCreate(SupplierPriceBase):
    supplier_sku: Optional[str] = None


class SupplierPriceResponse(SupplierPriceBase):
    id: int
    supplier_sku: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Price Comparison Schemas ====================

class PriceOption(BaseModel):
    """Single supplier price option in comparison."""
    rank: int
    supplier_id: int
    supplier_name: str
    supplier_code: str
    unit_cost: float
    case_cost: Optional[float] = None
    case_pack: int = 1
    landed_cost_per_unit: float
    effective_date: str
    price_age_hours: float
    in_stock: bool = True
    price_type: str = "list"
    promo_name: Optional[str] = None
    savings_vs_current: Optional[float] = None


class PriceStatistics(BaseModel):
    """Summary statistics for price comparison."""
    min_cost: float
    max_cost: float
    avg_cost: float
    spread: float
    potential_savings: Optional[float] = None


class ProductInfo(BaseModel):
    """Product info in comparison response."""
    id: int
    name: str
    department: Optional[str] = None
    current_cost: Optional[float] = None
    current_vendor: Optional[str] = None
    retail_price: Optional[float] = None
    pack_size: int = 1


class ScanResponse(BaseModel):
    """Response from scanning a UPC."""
    upc: str
    product: Optional[ProductInfo] = None
    prices: List[PriceOption] = []
    statistics: Optional[PriceStatistics] = None
    suppliers_checked: int = 0
    comparison_time: str
    error: Optional[str] = None


class BatchCompareRequest(BaseModel):
    """Request for batch comparison."""
    upcs: List[str]


class BatchCompareResponse(BaseModel):
    """Response from batch comparison."""
    comparisons: List[ScanResponse]
    summary: Dict[str, Any]


class SaveComparisonRequest(BaseModel):
    """Request to save a comparison result."""
    upc: str
    selected_supplier_id: int
    quantity: int = 1
    user_id: Optional[str] = None


class SaveComparisonResponse(BaseModel):
    """Response after saving comparison."""
    id: int
    status: str


# ==================== Manual Price Entry ====================

class ManualPriceEntry(BaseModel):
    """For manually entering supplier prices."""
    upc: str
    supplier_id: int
    unit_cost: float
    case_cost: Optional[float] = None
    case_pack: int = 1
    price_type: str = "list"
    promo_name: Optional[str] = None
    in_stock: bool = True
    notes: Optional[str] = None


class BulkPriceEntry(BaseModel):
    """For bulk price upload."""
    prices: List[ManualPriceEntry]


# ==================== Feed Sync ====================

class FeedSyncResponse(BaseModel):
    """Response from supplier feed sync."""
    supplier_id: int
    status: str
    records_processed: int
    records_created: int
    records_updated: int
    records_failed: int
    duration_seconds: Optional[float] = None

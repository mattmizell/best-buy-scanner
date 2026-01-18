"""
SQLAlchemy models for Best Buy Scanner.
Follows Lighthouse patterns adapted for retail UPC items.
"""

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, Text,
    ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Product(Base):
    """
    Master product catalog - seeded from CSE pricebook.
    """
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    upc = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    department = Column(String(100), index=True)

    # Current sourcing
    current_vendor = Column(String(100))
    current_cost = Column(Numeric(10, 4))
    retail_price = Column(Numeric(10, 2))
    pack_size = Column(Integer, default=1)

    # Inventory
    on_hand = Column(Integer, default=0)
    reorder_point = Column(Integer)
    reorder_qty = Column(Integer)

    # CSE sync tracking
    cse_item_id = Column(String(50))
    last_synced_at = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    supplier_prices = relationship("SupplierPrice", back_populates="product")
    comparisons = relationship("BestBuyComparison", back_populates="product")


class Supplier(Base):
    """
    Warehouse/distributor definitions.
    """
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(255), nullable=False)

    # Contact info
    contact_name = Column(String(100))
    phone = Column(String(20))
    email = Column(String(255))
    website = Column(String(255))

    # Account details
    account_number = Column(String(50))
    rep_name = Column(String(100))
    rep_phone = Column(String(20))

    # Ordering parameters
    min_order_amount = Column(Numeric(10, 2))
    min_order_cases = Column(Integer)
    order_lead_days = Column(Integer, default=2)
    delivery_days = Column(String(50))  # "Mon,Wed,Fri"

    # Feed configuration
    feed_type = Column(String(50))  # 'api', 'csv', 'edi', 'manual'
    feed_url = Column(String(500))
    feed_credentials = Column(JSON)
    last_feed_sync = Column(DateTime)
    feed_sync_frequency = Column(String(20))

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    prices = relationship("SupplierPrice", back_populates="supplier")
    shipping = relationship("SupplierShipping", back_populates="supplier")


class SupplierPrice(Base):
    """
    Price per UPC per supplier.
    Like Lighthouse ProductRealTimeCost.
    """
    __tablename__ = "supplier_prices"

    id = Column(Integer, primary_key=True, index=True)

    # Product reference
    upc = Column(String(20), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    supplier_sku = Column(String(50))  # Supplier's item code

    # Pricing
    unit_cost = Column(Numeric(10, 4), nullable=False)
    case_cost = Column(Numeric(10, 4))
    case_pack = Column(Integer, default=1)

    # Validity
    effective_date = Column(DateTime, nullable=False, index=True)
    expires_at = Column(DateTime)

    # Metadata
    price_type = Column(String(20), default='list')  # 'list', 'promo', 'contract'
    promo_name = Column(String(100))
    source = Column(String(50))  # 'feed', 'manual', 'api'

    # Availability
    in_stock = Column(Boolean, default=True)
    available_qty = Column(Integer)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    product = relationship("Product", back_populates="supplier_prices")
    supplier = relationship("Supplier", back_populates="prices")

    __table_args__ = (
        Index('idx_supplier_price_lookup', 'upc', 'supplier_id', 'effective_date'),
    )


class UPCAlias(Base):
    """
    Map supplier's product codes to standard UPC.
    Like Lighthouse ProductsAlias.
    """
    __tablename__ = "upc_aliases"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    supplier_sku = Column(String(50), nullable=False)
    supplier_name = Column(String(255))  # Supplier's product name
    standard_upc = Column(String(20), nullable=False, index=True)

    confidence = Column(Numeric(3, 2), default=1.0)
    match_method = Column(String(20))  # 'exact', 'fuzzy', 'manual'

    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(String(50))

    __table_args__ = (
        Index('idx_upc_alias_lookup', 'supplier_id', 'supplier_sku', unique=True),
    )


class SupplierShipping(Base):
    """
    Shipping costs per supplier for landed cost calculation.
    """
    __tablename__ = "supplier_shipping"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)

    method = Column(String(50), default='delivery')
    per_case_fee = Column(Numeric(10, 4))
    flat_fee = Column(Numeric(10, 2))
    free_shipping_threshold = Column(Numeric(10, 2))
    avg_delivery_cost = Column(Numeric(10, 2))

    effective_date = Column(DateTime, server_default=func.now())

    supplier = relationship("Supplier", back_populates="shipping")


class BestBuyComparison(Base):
    """
    Saved scan results with all price options.
    Like Lighthouse supply_options JSONB.
    """
    __tablename__ = "best_buy_comparisons"

    id = Column(Integer, primary_key=True, index=True)

    # What was scanned
    upc = Column(String(20), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    scanned_at = Column(DateTime, server_default=func.now())
    scanned_by = Column(String(50))

    # Current state at scan time
    current_cost = Column(Numeric(10, 4))
    current_vendor = Column(String(100))

    # Best option found
    best_supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    best_unit_cost = Column(Numeric(10, 4))
    savings_per_unit = Column(Numeric(10, 4))
    savings_percent = Column(Numeric(5, 2))

    # All options (JSONB)
    all_options = Column(JSON)

    # Action taken
    action = Column(String(20))  # 'ordered', 'saved', 'ignored'
    ordered_from_supplier_id = Column(Integer)
    order_qty = Column(Integer)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    product = relationship("Product", back_populates="comparisons")


class SupplierPriceFeed(Base):
    """
    Track data imports from supplier feeds.
    """
    __tablename__ = "supplier_price_feeds"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)

    feed_type = Column(String(50), nullable=False)
    feed_source = Column(String(255))

    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)
    status = Column(String(20), default='running')

    records_processed = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)

    error_message = Column(Text)
    error_details = Column(JSON)

    created_at = Column(DateTime, server_default=func.now())

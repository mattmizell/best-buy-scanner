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


# ============================================================
# ORDERING HUB MODELS
# ============================================================

class PurchaseOrder(Base):
    """
    Purchase order header - orders placed with suppliers.
    """
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    po_number = Column(String(50), unique=True, nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)

    # Status workflow: draft -> sent -> partial -> received -> closed
    status = Column(String(20), default='draft', index=True)

    # Dates
    created_at = Column(DateTime, server_default=func.now())
    sent_at = Column(DateTime)
    expected_delivery = Column(DateTime)
    closed_at = Column(DateTime)

    # Totals (calculated)
    total_items = Column(Integer, default=0)
    total_cases = Column(Integer, default=0)
    total_cost = Column(Numeric(12, 2), default=0)

    # Receiving summary
    items_received = Column(Integer, default=0)
    cases_received = Column(Integer, default=0)

    # Notes
    notes = Column(Text)
    created_by = Column(String(50))

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    supplier = relationship("Supplier")
    line_items = relationship("POLineItem", back_populates="purchase_order", cascade="all, delete-orphan")
    receiving_sessions = relationship("ReceivingSession", back_populates="purchase_order")


class POLineItem(Base):
    """
    Individual line items on a purchase order.
    """
    __tablename__ = "po_line_items"

    id = Column(Integer, primary_key=True, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)

    # Product info
    upc = Column(String(20), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    product_name = Column(String(255))  # Denormalized for convenience

    # What was ordered
    qty_ordered = Column(Integer, nullable=False)
    unit_cost = Column(Numeric(10, 4), nullable=False)
    case_pack = Column(Integer, default=1)
    line_total = Column(Numeric(10, 2))

    # Receiving tracking
    qty_received = Column(Integer, default=0)
    qty_pending = Column(Integer)  # Calculated: ordered - received

    # Status
    status = Column(String(20), default='pending')  # pending, partial, received, over, short

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="line_items")
    product = relationship("Product")
    receiving_items = relationship("ReceivingItem", back_populates="po_line_item")

    __table_args__ = (
        Index('idx_po_line_lookup', 'po_id', 'upc'),
    )


class ReceivingSession(Base):
    """
    A receiving event - when a delivery arrives.
    """
    __tablename__ = "receiving_sessions"

    id = Column(Integer, primary_key=True, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)

    # Session info
    received_at = Column(DateTime, server_default=func.now())
    received_by = Column(String(50))

    # Delivery details
    invoice_number = Column(String(50))
    delivery_ticket = Column(String(50))

    # Totals
    total_items = Column(Integer, default=0)
    total_cases = Column(Integer, default=0)

    # Discrepancy summary
    items_short = Column(Integer, default=0)
    items_over = Column(Integer, default=0)
    items_damaged = Column(Integer, default=0)

    notes = Column(Text)
    status = Column(String(20), default='in_progress')  # in_progress, completed

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="receiving_sessions")
    supplier = relationship("Supplier")
    items = relationship("ReceivingItem", back_populates="receiving_session", cascade="all, delete-orphan")


class ReceivingItem(Base):
    """
    Individual items received in a receiving session.
    """
    __tablename__ = "receiving_items"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("receiving_sessions.id"), nullable=False, index=True)
    po_line_id = Column(Integer, ForeignKey("po_line_items.id"), index=True)

    # Product info
    upc = Column(String(20), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    product_name = Column(String(255))

    # What was received
    qty_received = Column(Integer, nullable=False)
    qty_expected = Column(Integer)  # From PO line if linked

    # Condition
    qty_good = Column(Integer)
    qty_damaged = Column(Integer, default=0)

    # Discrepancy
    discrepancy_type = Column(String(20))  # null, short, over, damaged, wrong_item
    discrepancy_qty = Column(Integer)
    discrepancy_notes = Column(Text)

    scanned_at = Column(DateTime, server_default=func.now())

    # Relationships
    receiving_session = relationship("ReceivingSession", back_populates="items")
    po_line_item = relationship("POLineItem", back_populates="receiving_items")
    product = relationship("Product")

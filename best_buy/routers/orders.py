"""
Orders API - Purchase order management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from ..database import get_db
from ..models import (
    PurchaseOrder, POLineItem, Product, Supplier, SupplierPrice
)

router = APIRouter(prefix="/orders", tags=["Orders"])


def generate_po_number(db: Session, supplier_code: str) -> str:
    """Generate a unique PO number: PO-{supplier_code}-{YYYYMMDD}-{seq}"""
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"PO-{supplier_code}-{today}"

    # Find existing POs with this prefix
    existing = db.query(PurchaseOrder).filter(
        PurchaseOrder.po_number.like(f"{prefix}%")
    ).count()

    return f"{prefix}-{existing + 1:03d}"


@router.get("")
async def list_orders(
    status: Optional[str] = None,
    supplier_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    List purchase orders.

    - **status**: Filter by status (draft, sent, partial, received, closed)
    - **supplier_id**: Filter by supplier
    - **limit**: Max results (default 50)
    """
    query = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.supplier)
    )

    if status:
        query = query.filter(PurchaseOrder.status == status)
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)

    orders = query.order_by(desc(PurchaseOrder.created_at)).limit(limit).all()

    return [
        {
            "id": po.id,
            "po_number": po.po_number,
            "supplier_id": po.supplier_id,
            "supplier_name": po.supplier.name if po.supplier else None,
            "status": po.status,
            "total_items": po.total_items,
            "total_cases": po.total_cases,
            "total_cost": float(po.total_cost) if po.total_cost else 0,
            "items_received": po.items_received,
            "created_at": po.created_at.isoformat() if po.created_at else None,
            "sent_at": po.sent_at.isoformat() if po.sent_at else None,
            "expected_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
        }
        for po in orders
    ]


@router.post("")
async def create_order(
    supplier_id: int,
    notes: Optional[str] = None,
    created_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Create a new purchase order (draft).
    """
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")

    po_number = generate_po_number(db, supplier.code)

    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=supplier_id,
        status="draft",
        notes=notes,
        created_by=created_by
    )

    db.add(po)
    db.commit()
    db.refresh(po)

    return {
        "id": po.id,
        "po_number": po.po_number,
        "supplier_id": po.supplier_id,
        "supplier_name": supplier.name,
        "status": po.status,
        "created_at": po.created_at.isoformat()
    }


@router.get("/{po_id}")
async def get_order(po_id: int, db: Session = Depends(get_db)):
    """
    Get purchase order details with line items.
    """
    po = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.supplier),
        joinedload(PurchaseOrder.line_items).joinedload(POLineItem.product)
    ).get(po_id)

    if not po:
        raise HTTPException(404, "Order not found")

    return {
        "id": po.id,
        "po_number": po.po_number,
        "supplier_id": po.supplier_id,
        "supplier_name": po.supplier.name if po.supplier else None,
        "supplier_email": po.supplier.email if po.supplier else None,
        "status": po.status,
        "total_items": po.total_items,
        "total_cases": po.total_cases,
        "total_cost": float(po.total_cost) if po.total_cost else 0,
        "items_received": po.items_received,
        "cases_received": po.cases_received,
        "notes": po.notes,
        "created_by": po.created_by,
        "created_at": po.created_at.isoformat() if po.created_at else None,
        "sent_at": po.sent_at.isoformat() if po.sent_at else None,
        "expected_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
        "line_items": [
            {
                "id": item.id,
                "upc": item.upc,
                "product_name": item.product_name,
                "qty_ordered": item.qty_ordered,
                "unit_cost": float(item.unit_cost) if item.unit_cost else 0,
                "case_pack": item.case_pack,
                "line_total": float(item.line_total) if item.line_total else 0,
                "qty_received": item.qty_received,
                "status": item.status
            }
            for item in po.line_items
        ]
    }


@router.post("/{po_id}/items")
async def add_item_to_order(
    po_id: int,
    upc: str,
    qty: int,
    unit_cost: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """
    Add an item to a purchase order.

    If unit_cost is not provided, will use the supplier's current price.
    """
    po = db.query(PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Order not found")

    if po.status not in ("draft", "sent"):
        raise HTTPException(400, f"Cannot add items to {po.status} order")

    # Get product info
    product = db.query(Product).filter(Product.upc == upc).first()
    product_name = product.name if product else f"UPC: {upc}"
    product_id = product.id if product else None

    # Get supplier price if not provided
    if unit_cost is None:
        supplier_price = db.query(SupplierPrice).filter(
            SupplierPrice.upc == upc,
            SupplierPrice.supplier_id == po.supplier_id
        ).order_by(desc(SupplierPrice.effective_date)).first()

        if supplier_price:
            unit_cost = float(supplier_price.unit_cost)
            case_pack = supplier_price.case_pack or 1
        else:
            unit_cost = 0
            case_pack = 1
    else:
        case_pack = 1

    # Check if item already on PO
    existing = db.query(POLineItem).filter(
        POLineItem.po_id == po_id,
        POLineItem.upc == upc
    ).first()

    if existing:
        # Update quantity
        existing.qty_ordered += qty
        existing.line_total = Decimal(str(existing.qty_ordered * unit_cost))
        existing.qty_pending = existing.qty_ordered - existing.qty_received
        item = existing
    else:
        # Create new line item
        item = POLineItem(
            po_id=po_id,
            upc=upc,
            product_id=product_id,
            product_name=product_name,
            qty_ordered=qty,
            unit_cost=Decimal(str(unit_cost)),
            case_pack=case_pack,
            line_total=Decimal(str(qty * unit_cost)),
            qty_pending=qty
        )
        db.add(item)

    # Update PO totals
    db.flush()
    _update_po_totals(db, po)

    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "upc": item.upc,
        "product_name": item.product_name,
        "qty_ordered": item.qty_ordered,
        "unit_cost": float(item.unit_cost),
        "line_total": float(item.line_total),
        "po_total_cost": float(po.total_cost)
    }


@router.delete("/{po_id}/items/{item_id}")
async def remove_item_from_order(
    po_id: int,
    item_id: int,
    db: Session = Depends(get_db)
):
    """Remove an item from a purchase order."""
    po = db.query(PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Order not found")

    if po.status not in ("draft",):
        raise HTTPException(400, f"Cannot remove items from {po.status} order")

    item = db.query(POLineItem).filter(
        POLineItem.id == item_id,
        POLineItem.po_id == po_id
    ).first()

    if not item:
        raise HTTPException(404, "Item not found")

    db.delete(item)
    _update_po_totals(db, po)
    db.commit()

    return {"status": "deleted", "po_total_cost": float(po.total_cost)}


@router.post("/{po_id}/send")
async def send_order(
    po_id: int,
    expected_delivery: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Mark order as sent to supplier.
    """
    po = db.query(PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Order not found")

    if po.status != "draft":
        raise HTTPException(400, f"Can only send draft orders, current status: {po.status}")

    if po.total_items == 0:
        raise HTTPException(400, "Cannot send empty order")

    po.status = "sent"
    po.sent_at = datetime.now()

    if expected_delivery:
        po.expected_delivery = datetime.fromisoformat(expected_delivery)

    db.commit()

    return {
        "id": po.id,
        "po_number": po.po_number,
        "status": po.status,
        "sent_at": po.sent_at.isoformat()
    }


@router.post("/{po_id}/close")
async def close_order(po_id: int, db: Session = Depends(get_db)):
    """
    Close a purchase order.
    """
    po = db.query(PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Order not found")

    po.status = "closed"
    po.closed_at = datetime.now()
    db.commit()

    return {
        "id": po.id,
        "po_number": po.po_number,
        "status": po.status,
        "closed_at": po.closed_at.isoformat()
    }


@router.delete("/{po_id}")
async def delete_order(po_id: int, db: Session = Depends(get_db)):
    """
    Delete a draft purchase order.
    """
    po = db.query(PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Order not found")

    if po.status != "draft":
        raise HTTPException(400, "Can only delete draft orders")

    db.delete(po)
    db.commit()

    return {"status": "deleted"}


def _update_po_totals(db: Session, po: PurchaseOrder):
    """Recalculate PO totals from line items."""
    items = db.query(POLineItem).filter(POLineItem.po_id == po.id).all()

    po.total_items = len(items)
    po.total_cases = sum(item.qty_ordered for item in items)
    po.total_cost = sum(item.line_total or 0 for item in items)
    po.items_received = sum(1 for item in items if item.qty_received > 0)
    po.cases_received = sum(item.qty_received for item in items)

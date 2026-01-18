"""
Receiving API - Receive deliveries against purchase orders.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from ..database import get_db
from ..models import (
    PurchaseOrder, POLineItem, Product, Supplier,
    ReceivingSession, ReceivingItem
)

router = APIRouter(prefix="/receiving", tags=["Receiving"])


@router.get("/sessions")
async def list_sessions(
    po_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    List receiving sessions.
    """
    query = db.query(ReceivingSession).options(
        joinedload(ReceivingSession.supplier),
        joinedload(ReceivingSession.purchase_order)
    )

    if po_id:
        query = query.filter(ReceivingSession.po_id == po_id)
    if supplier_id:
        query = query.filter(ReceivingSession.supplier_id == supplier_id)
    if status:
        query = query.filter(ReceivingSession.status == status)

    sessions = query.order_by(desc(ReceivingSession.received_at)).limit(limit).all()

    return [
        {
            "id": s.id,
            "po_id": s.po_id,
            "po_number": s.purchase_order.po_number if s.purchase_order else None,
            "supplier_id": s.supplier_id,
            "supplier_name": s.supplier.name if s.supplier else None,
            "received_at": s.received_at.isoformat() if s.received_at else None,
            "received_by": s.received_by,
            "invoice_number": s.invoice_number,
            "total_items": s.total_items,
            "total_cases": s.total_cases,
            "items_short": s.items_short,
            "items_over": s.items_over,
            "items_damaged": s.items_damaged,
            "status": s.status
        }
        for s in sessions
    ]


@router.post("/sessions")
async def start_receiving_session(
    po_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    invoice_number: Optional[str] = None,
    delivery_ticket: Optional[str] = None,
    received_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Start a new receiving session.

    Can receive against a PO, or just log a delivery from a supplier.
    """
    # Must have either po_id or supplier_id
    if not po_id and not supplier_id:
        raise HTTPException(400, "Must provide po_id or supplier_id")

    # If PO provided, get supplier from it
    if po_id:
        po = db.query(PurchaseOrder).get(po_id)
        if not po:
            raise HTTPException(404, "Purchase order not found")
        supplier_id = po.supplier_id

        # Update PO status if this is first receiving
        if po.status == "sent":
            po.status = "partial"
    else:
        # Verify supplier exists
        supplier = db.query(Supplier).get(supplier_id)
        if not supplier:
            raise HTTPException(404, "Supplier not found")

    session = ReceivingSession(
        po_id=po_id,
        supplier_id=supplier_id,
        invoice_number=invoice_number,
        delivery_ticket=delivery_ticket,
        received_by=received_by,
        status="in_progress"
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    # Get expected items if receiving against PO
    expected_items = []
    if po_id:
        po_items = db.query(POLineItem).filter(
            POLineItem.po_id == po_id,
            POLineItem.qty_pending > 0
        ).all()

        expected_items = [
            {
                "po_line_id": item.id,
                "upc": item.upc,
                "product_name": item.product_name,
                "qty_ordered": item.qty_ordered,
                "qty_received": item.qty_received,
                "qty_pending": item.qty_pending
            }
            for item in po_items
        ]

    return {
        "id": session.id,
        "po_id": session.po_id,
        "supplier_id": session.supplier_id,
        "status": session.status,
        "expected_items": expected_items
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: int, db: Session = Depends(get_db)):
    """
    Get receiving session details with items received.
    """
    session = db.query(ReceivingSession).options(
        joinedload(ReceivingSession.supplier),
        joinedload(ReceivingSession.purchase_order),
        joinedload(ReceivingSession.items)
    ).get(session_id)

    if not session:
        raise HTTPException(404, "Session not found")

    # Get expected items if PO-based
    expected_items = []
    if session.po_id:
        po_items = db.query(POLineItem).filter(
            POLineItem.po_id == session.po_id
        ).all()

        expected_items = [
            {
                "po_line_id": item.id,
                "upc": item.upc,
                "product_name": item.product_name,
                "qty_ordered": item.qty_ordered,
                "qty_received": item.qty_received,
                "qty_pending": item.qty_ordered - item.qty_received
            }
            for item in po_items
        ]

    return {
        "id": session.id,
        "po_id": session.po_id,
        "po_number": session.purchase_order.po_number if session.purchase_order else None,
        "supplier_id": session.supplier_id,
        "supplier_name": session.supplier.name if session.supplier else None,
        "received_at": session.received_at.isoformat() if session.received_at else None,
        "received_by": session.received_by,
        "invoice_number": session.invoice_number,
        "delivery_ticket": session.delivery_ticket,
        "total_items": session.total_items,
        "total_cases": session.total_cases,
        "items_short": session.items_short,
        "items_over": session.items_over,
        "items_damaged": session.items_damaged,
        "status": session.status,
        "notes": session.notes,
        "expected_items": expected_items,
        "received_items": [
            {
                "id": item.id,
                "upc": item.upc,
                "product_name": item.product_name,
                "qty_received": item.qty_received,
                "qty_expected": item.qty_expected,
                "qty_good": item.qty_good,
                "qty_damaged": item.qty_damaged,
                "discrepancy_type": item.discrepancy_type,
                "discrepancy_qty": item.discrepancy_qty,
                "discrepancy_notes": item.discrepancy_notes,
                "scanned_at": item.scanned_at.isoformat() if item.scanned_at else None
            }
            for item in session.items
        ]
    }


@router.post("/sessions/{session_id}/receive")
async def receive_item(
    session_id: int,
    upc: str,
    qty_received: int,
    qty_damaged: int = 0,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Receive an item in a session.

    Scan a UPC and record quantity received.
    """
    session = db.query(ReceivingSession).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if session.status == "completed":
        raise HTTPException(400, "Session already completed")

    # Get product info
    product = db.query(Product).filter(Product.upc == upc).first()
    product_name = product.name if product else f"UPC: {upc}"
    product_id = product.id if product else None

    # Find matching PO line item if receiving against PO
    po_line = None
    qty_expected = None
    discrepancy_type = None
    discrepancy_qty = None

    if session.po_id:
        po_line = db.query(POLineItem).filter(
            POLineItem.po_id == session.po_id,
            POLineItem.upc == upc
        ).first()

        if po_line:
            qty_expected = po_line.qty_ordered - po_line.qty_received

            # Calculate discrepancy
            qty_good = qty_received - qty_damaged
            if qty_good < qty_expected:
                discrepancy_type = "short"
                discrepancy_qty = qty_expected - qty_good
            elif qty_good > qty_expected:
                discrepancy_type = "over"
                discrepancy_qty = qty_good - qty_expected

            if qty_damaged > 0 and not discrepancy_type:
                discrepancy_type = "damaged"
                discrepancy_qty = qty_damaged

            # Update PO line item
            po_line.qty_received += qty_received
            po_line.qty_pending = po_line.qty_ordered - po_line.qty_received

            if po_line.qty_received >= po_line.qty_ordered:
                po_line.status = "received"
            elif po_line.qty_received > 0:
                po_line.status = "partial"
        else:
            # Item not on PO - mark as unexpected
            discrepancy_type = "wrong_item"

    # Create receiving item record
    recv_item = ReceivingItem(
        session_id=session_id,
        po_line_id=po_line.id if po_line else None,
        upc=upc,
        product_id=product_id,
        product_name=product_name,
        qty_received=qty_received,
        qty_expected=qty_expected,
        qty_good=qty_received - qty_damaged,
        qty_damaged=qty_damaged,
        discrepancy_type=discrepancy_type,
        discrepancy_qty=discrepancy_qty,
        discrepancy_notes=notes
    )

    db.add(recv_item)

    # Update session totals
    session.total_items += 1
    session.total_cases += qty_received

    if discrepancy_type == "short":
        session.items_short += 1
    elif discrepancy_type == "over":
        session.items_over += 1
    elif discrepancy_type == "damaged" or qty_damaged > 0:
        session.items_damaged += 1

    # Update PO totals if applicable
    if session.po_id:
        _update_po_receiving_totals(db, session.po_id)

    db.commit()
    db.refresh(recv_item)

    return {
        "id": recv_item.id,
        "upc": recv_item.upc,
        "product_name": recv_item.product_name,
        "qty_received": recv_item.qty_received,
        "qty_expected": recv_item.qty_expected,
        "qty_good": recv_item.qty_good,
        "qty_damaged": recv_item.qty_damaged,
        "discrepancy_type": recv_item.discrepancy_type,
        "discrepancy_qty": recv_item.discrepancy_qty,
        "on_po": po_line is not None,
        "session_totals": {
            "total_items": session.total_items,
            "total_cases": session.total_cases,
            "items_short": session.items_short,
            "items_over": session.items_over,
            "items_damaged": session.items_damaged
        }
    }


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Complete a receiving session.
    """
    session = db.query(ReceivingSession).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    session.status = "completed"
    if notes:
        session.notes = notes

    # Update PO status if all items received
    if session.po_id:
        po = db.query(PurchaseOrder).get(session.po_id)
        pending_items = db.query(POLineItem).filter(
            POLineItem.po_id == session.po_id,
            POLineItem.qty_pending > 0
        ).count()

        if pending_items == 0:
            po.status = "received"
        else:
            po.status = "partial"

    db.commit()

    return {
        "id": session.id,
        "status": session.status,
        "total_items": session.total_items,
        "total_cases": session.total_cases,
        "items_short": session.items_short,
        "items_over": session.items_over,
        "items_damaged": session.items_damaged,
        "po_status": po.status if session.po_id else None
    }


@router.get("/po/{po_id}/status")
async def get_po_receiving_status(po_id: int, db: Session = Depends(get_db)):
    """
    Get receiving status for a purchase order.

    Shows what's been received vs what's expected.
    """
    po = db.query(PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Purchase order not found")

    line_items = db.query(POLineItem).filter(POLineItem.po_id == po_id).all()

    items = [
        {
            "id": item.id,
            "upc": item.upc,
            "product_name": item.product_name,
            "qty_ordered": item.qty_ordered,
            "qty_received": item.qty_received,
            "qty_pending": item.qty_ordered - item.qty_received,
            "status": item.status,
            "percent_received": round((item.qty_received / item.qty_ordered) * 100, 1) if item.qty_ordered > 0 else 0
        }
        for item in line_items
    ]

    total_ordered = sum(item.qty_ordered for item in line_items)
    total_received = sum(item.qty_received for item in line_items)

    return {
        "po_id": po.id,
        "po_number": po.po_number,
        "status": po.status,
        "total_ordered": total_ordered,
        "total_received": total_received,
        "percent_complete": round((total_received / total_ordered) * 100, 1) if total_ordered > 0 else 0,
        "items": items
    }


def _update_po_receiving_totals(db: Session, po_id: int):
    """Update PO receiving totals from line items."""
    po = db.query(PurchaseOrder).get(po_id)
    items = db.query(POLineItem).filter(POLineItem.po_id == po_id).all()

    po.items_received = sum(1 for item in items if item.qty_received > 0)
    po.cases_received = sum(item.qty_received for item in items)

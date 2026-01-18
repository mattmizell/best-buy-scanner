"""
Cart API - Order cart for Best Buy Scanner.
Items are added from scanner, grouped by supplier, then converted to POs.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from collections import defaultdict

from ..database import get_db
from ..models import (
    OrderCartItem, PurchaseOrder, POLineItem,
    Product, Supplier, SupplierPrice
)

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("")
async def get_cart(db: Session = Depends(get_db)):
    """
    Get cart contents grouped by supplier.
    Shows how many POs will be created.
    """
    items = db.query(OrderCartItem).options(
        joinedload(OrderCartItem.supplier),
        joinedload(OrderCartItem.product)
    ).order_by(OrderCartItem.supplier_id, OrderCartItem.added_at).all()

    # Group by supplier
    by_supplier = defaultdict(list)
    for item in items:
        by_supplier[item.supplier_id].append(item)

    suppliers = []
    total_items = 0
    total_cost = Decimal('0')

    for supplier_id, supplier_items in by_supplier.items():
        supplier = supplier_items[0].supplier
        supplier_total = sum(
            Decimal(str(item.unit_cost)) * item.quantity
            for item in supplier_items
        )
        supplier_cases = sum(item.quantity for item in supplier_items)

        suppliers.append({
            "supplier_id": supplier_id,
            "supplier_name": supplier.name,
            "supplier_code": supplier.code,
            "item_count": len(supplier_items),
            "total_cases": supplier_cases,
            "total_cost": float(supplier_total),
            "items": [
                {
                    "id": item.id,
                    "upc": item.upc,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_cost": float(item.unit_cost),
                    "line_total": float(Decimal(str(item.unit_cost)) * item.quantity),
                    "added_at": item.added_at.isoformat() if item.added_at else None
                }
                for item in supplier_items
            ]
        })

        total_items += len(supplier_items)
        total_cost += supplier_total

    return {
        "po_count": len(suppliers),
        "total_items": total_items,
        "total_cost": float(total_cost),
        "suppliers": suppliers
    }


@router.post("")
async def add_to_cart(
    upc: str,
    supplier_id: int,
    quantity: int = 1,
    unit_cost: Optional[float] = None,
    added_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Add an item to the cart from Best Buy Scanner.

    Called when user taps "Order from [Supplier]" on a price.
    """
    # Verify supplier exists
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")

    # Get product info
    product = db.query(Product).filter(Product.upc == upc).first()
    product_name = product.name if product else f"UPC: {upc}"
    product_id = product.id if product else None

    # Get price if not provided
    if unit_cost is None:
        price = db.query(SupplierPrice).filter(
            SupplierPrice.upc == upc,
            SupplierPrice.supplier_id == supplier_id
        ).order_by(desc(SupplierPrice.effective_date)).first()

        if price:
            unit_cost = float(price.unit_cost)
            case_pack = price.case_pack or 1
        else:
            raise HTTPException(400, "No price found for this item from this supplier")
    else:
        case_pack = 1

    # Check if already in cart for same supplier
    existing = db.query(OrderCartItem).filter(
        OrderCartItem.upc == upc,
        OrderCartItem.supplier_id == supplier_id
    ).first()

    if existing:
        # Update quantity
        existing.quantity += quantity
        item = existing
    else:
        # Add new cart item
        item = OrderCartItem(
            upc=upc,
            product_id=product_id,
            product_name=product_name,
            supplier_id=supplier_id,
            quantity=quantity,
            unit_cost=Decimal(str(unit_cost)),
            case_pack=case_pack,
            added_by=added_by
        )
        db.add(item)

    db.commit()
    db.refresh(item)

    # Get updated cart summary
    cart_count = db.query(OrderCartItem).count()
    supplier_count = db.query(OrderCartItem.supplier_id).distinct().count()

    return {
        "id": item.id,
        "upc": item.upc,
        "product_name": item.product_name,
        "supplier_name": supplier.name,
        "quantity": item.quantity,
        "unit_cost": float(item.unit_cost),
        "cart_summary": {
            "total_items": cart_count,
            "po_count": supplier_count
        }
    }


@router.delete("/{item_id}")
async def remove_from_cart(item_id: int, db: Session = Depends(get_db)):
    """Remove an item from the cart."""
    item = db.query(OrderCartItem).get(item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    db.delete(item)
    db.commit()

    return {"status": "removed"}


@router.delete("")
async def clear_cart(db: Session = Depends(get_db)):
    """Clear all items from the cart."""
    db.query(OrderCartItem).delete()
    db.commit()
    return {"status": "cleared"}


@router.post("/create-pos")
async def create_pos_from_cart(
    created_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Create purchase orders from cart.

    Creates one PO per supplier with all their items.
    Clears cart after POs are created.
    """
    items = db.query(OrderCartItem).options(
        joinedload(OrderCartItem.supplier)
    ).all()

    if not items:
        raise HTTPException(400, "Cart is empty")

    # Group by supplier
    by_supplier = defaultdict(list)
    for item in items:
        by_supplier[item.supplier_id].append(item)

    created_pos = []

    for supplier_id, supplier_items in by_supplier.items():
        supplier = supplier_items[0].supplier

        # Generate PO number
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"PO-{supplier.code}-{today}"
        existing = db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number.like(f"{prefix}%")
        ).count()
        po_number = f"{prefix}-{existing + 1:03d}"

        # Create PO
        po = PurchaseOrder(
            po_number=po_number,
            supplier_id=supplier_id,
            status="draft",
            created_by=created_by
        )
        db.add(po)
        db.flush()  # Get PO id

        # Add line items
        total_cost = Decimal('0')
        for cart_item in supplier_items:
            line_total = Decimal(str(cart_item.unit_cost)) * cart_item.quantity

            line = POLineItem(
                po_id=po.id,
                upc=cart_item.upc,
                product_id=cart_item.product_id,
                product_name=cart_item.product_name,
                qty_ordered=cart_item.quantity,
                unit_cost=cart_item.unit_cost,
                case_pack=cart_item.case_pack,
                line_total=line_total,
                qty_pending=cart_item.quantity
            )
            db.add(line)
            total_cost += line_total

        # Update PO totals
        po.total_items = len(supplier_items)
        po.total_cases = sum(item.quantity for item in supplier_items)
        po.total_cost = total_cost

        created_pos.append({
            "id": po.id,
            "po_number": po.po_number,
            "supplier_name": supplier.name,
            "item_count": len(supplier_items),
            "total_cost": float(total_cost)
        })

    # Clear cart
    db.query(OrderCartItem).delete()

    db.commit()

    return {
        "pos_created": len(created_pos),
        "purchase_orders": created_pos
    }


@router.get("/summary")
async def get_cart_summary(db: Session = Depends(get_db)):
    """Get quick cart summary for badge display."""
    total_items = db.query(OrderCartItem).count()
    supplier_count = db.query(OrderCartItem.supplier_id).distinct().count()

    total_cost = db.query(
        func.sum(OrderCartItem.unit_cost * OrderCartItem.quantity)
    ).scalar() or 0

    return {
        "total_items": total_items,
        "po_count": supplier_count,
        "total_cost": float(total_cost)
    }

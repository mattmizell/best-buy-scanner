"""
Suppliers API - Manage suppliers and their prices.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..service import BestBuyService
from ..models import Supplier, SupplierPrice, Product
from .. import schemas

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.get("/", response_model=List[schemas.SupplierResponse])
async def list_suppliers(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List all configured suppliers."""
    service = BestBuyService(db)
    return service.get_all_suppliers(active_only=active_only)


@router.get("/{supplier_id}", response_model=schemas.SupplierResponse)
async def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific supplier."""
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    return supplier


@router.post("/", response_model=schemas.SupplierResponse)
async def create_supplier(
    supplier: schemas.SupplierCreate,
    db: Session = Depends(get_db)
):
    """Create a new supplier."""
    # Check if code already exists
    existing = db.query(Supplier).filter(Supplier.code == supplier.code).first()
    if existing:
        raise HTTPException(400, f"Supplier with code '{supplier.code}' already exists")

    db_supplier = Supplier(**supplier.model_dump())
    db.add(db_supplier)
    db.commit()
    db.refresh(db_supplier)
    return db_supplier


@router.put("/{supplier_id}", response_model=schemas.SupplierResponse)
async def update_supplier(
    supplier_id: int,
    supplier: schemas.SupplierCreate,
    db: Session = Depends(get_db)
):
    """Update a supplier."""
    db_supplier = db.query(Supplier).get(supplier_id)
    if not db_supplier:
        raise HTTPException(404, "Supplier not found")

    for key, value in supplier.model_dump().items():
        setattr(db_supplier, key, value)

    db.commit()
    db.refresh(db_supplier)
    return db_supplier


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    """Deactivate a supplier (soft delete)."""
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")

    supplier.is_active = False
    db.commit()
    return {"status": "deactivated", "supplier_id": supplier_id}


# ==================== Supplier Prices ====================

@router.get("/{supplier_id}/prices", response_model=List[schemas.SupplierPriceResponse])
async def get_supplier_prices(
    supplier_id: int,
    department: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all prices from a supplier."""
    service = BestBuyService(db)
    return service.get_supplier_prices(
        supplier_id=supplier_id,
        department=department,
        limit=limit
    )


@router.post("/{supplier_id}/prices", response_model=schemas.SupplierPriceResponse)
async def add_supplier_price(
    supplier_id: int,
    price: schemas.ManualPriceEntry,
    db: Session = Depends(get_db)
):
    """
    Add a price for a supplier.

    Used for manual price entry.
    """
    # Verify supplier exists
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")

    service = BestBuyService(db)
    result = service.add_supplier_price(
        upc=price.upc,
        supplier_id=supplier_id,
        unit_cost=price.unit_cost,
        case_cost=price.case_cost,
        case_pack=price.case_pack,
        price_type=price.price_type,
        promo_name=price.promo_name,
        in_stock=price.in_stock
    )

    return result


@router.post("/{supplier_id}/prices/bulk")
async def bulk_add_prices(
    supplier_id: int,
    request: schemas.BulkPriceEntry,
    db: Session = Depends(get_db)
):
    """
    Add multiple prices at once.

    Used for uploading price lists.
    """
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")

    service = BestBuyService(db)
    results = {"created": 0, "failed": 0, "errors": []}

    for price in request.prices:
        try:
            service.add_supplier_price(
                upc=price.upc,
                supplier_id=supplier_id,
                unit_cost=price.unit_cost,
                case_cost=price.case_cost,
                case_pack=price.case_pack,
                price_type=price.price_type,
                promo_name=price.promo_name,
                in_stock=price.in_stock
            )
            results["created"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"upc": price.upc, "error": str(e)})

    return results

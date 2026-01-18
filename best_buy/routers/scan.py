"""
Scan API - Main scanning and price comparison endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..service import BestBuyService
from .. import schemas

router = APIRouter(prefix="/scan", tags=["Scan"])


@router.get("/{upc}", response_model=schemas.ScanResponse)
async def scan_upc(
    upc: str,
    max_age_hours: int = 168,
    include_out_of_stock: bool = False,
    db: Session = Depends(get_db)
):
    """
    Scan a UPC barcode and get price comparison.

    This is the main mobile scanning endpoint.

    - **upc**: The UPC barcode (12 or 13 digits)
    - **max_age_hours**: Only include prices newer than this (default 7 days)
    - **include_out_of_stock**: Include out of stock items
    """
    service = BestBuyService(db)
    result = service.get_best_prices_for_upc(
        upc=upc,
        max_age_hours=max_age_hours,
        include_out_of_stock=include_out_of_stock
    )
    return result


@router.post("/batch", response_model=schemas.BatchCompareResponse)
async def batch_compare(
    request: schemas.BatchCompareRequest,
    db: Session = Depends(get_db)
):
    """
    Compare multiple UPCs at once.

    Useful for scanning a shelf or category.
    """
    service = BestBuyService(db)
    result = service.batch_compare(request.upcs)
    return result


@router.post("/save", response_model=schemas.SaveComparisonResponse)
async def save_comparison(
    request: schemas.SaveComparisonRequest,
    db: Session = Depends(get_db)
):
    """
    Save a comparison result.

    Called after user reviews comparison and wants to track it.
    """
    service = BestBuyService(db)

    # Get fresh comparison
    comparison_data = service.get_best_prices_for_upc(request.upc)

    if comparison_data.get("error"):
        raise HTTPException(404, comparison_data["error"])

    saved = service.save_comparison(
        upc=request.upc,
        comparison_data=comparison_data,
        selected_supplier_id=request.selected_supplier_id,
        quantity=request.quantity,
        user_id=request.user_id
    )

    return {"id": saved.id, "status": "saved"}


@router.get("/product/{product_id}")
async def get_product_prices(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get price comparison for a product by ID."""
    from ..models import Product

    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    service = BestBuyService(db)
    return service.get_best_prices_for_upc(product.upc)

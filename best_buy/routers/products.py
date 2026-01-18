"""
Products API - Manage product catalog.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..models import Product
from .. import schemas

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("/", response_model=List[schemas.ProductResponse])
async def list_products(
    department: Optional[str] = None,
    vendor: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List products with optional filtering.

    - **department**: Filter by department name
    - **vendor**: Filter by current vendor
    - **search**: Search product name
    - **limit**: Max results (default 100, max 500)
    - **offset**: Pagination offset
    """
    query = db.query(Product)

    if department:
        query = query.filter(Product.department == department)

    if vendor:
        query = query.filter(Product.current_vendor == vendor)

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    total = query.count()

    products = query.order_by(Product.name).offset(offset).limit(limit).all()

    return products


@router.get("/departments")
async def list_departments(db: Session = Depends(get_db)):
    """Get list of all departments."""
    results = db.query(Product.department).distinct().filter(
        Product.department.isnot(None)
    ).order_by(Product.department).all()

    return [r[0] for r in results]


@router.get("/vendors")
async def list_vendors(db: Session = Depends(get_db)):
    """Get list of all current vendors."""
    results = db.query(Product.current_vendor).distinct().filter(
        Product.current_vendor.isnot(None)
    ).order_by(Product.current_vendor).all()

    return [r[0] for r in results]


@router.get("/stats")
async def get_product_stats(db: Session = Depends(get_db)):
    """Get product catalog statistics."""
    total = db.query(Product).count()

    with_cost = db.query(Product).filter(Product.current_cost.isnot(None)).count()

    with_vendor = db.query(Product).filter(Product.current_vendor.isnot(None)).count()

    departments = db.query(Product.department).distinct().count()

    return {
        "total_products": total,
        "products_with_cost": with_cost,
        "products_with_vendor": with_vendor,
        "departments": departments
    }


@router.get("/{product_id}", response_model=schemas.ProductResponse)
async def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific product."""
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/upc/{upc}", response_model=schemas.ProductResponse)
async def get_product_by_upc(
    upc: str,
    db: Session = Depends(get_db)
):
    """Get a product by UPC."""
    product = db.query(Product).filter(Product.upc == upc).first()
    if not product:
        raise HTTPException(404, f"Product not found with UPC: {upc}")
    return product


@router.put("/{product_id}", response_model=schemas.ProductResponse)
async def update_product(
    product_id: int,
    product_update: schemas.ProductCreate,
    db: Session = Depends(get_db)
):
    """Update a product."""
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    for key, value in product_update.model_dump(exclude_unset=True).items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product

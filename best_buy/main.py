"""
Best Buy Scanner - FastAPI Application

Run with:
    cd cse_integration
    uvicorn best_buy.main:app --reload --port 8000

Deploy to Render:
    uvicorn best_buy.main:app --host 0.0.0.0 --port $PORT
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .database import init_db, SessionLocal
from .routers import scan, suppliers, products, orders, receiving, cart

# Initialize app
app = FastAPI(
    title="Best Buy Scanner",
    description="Scan items and find the best wholesale prices",
    version="1.0.0"
)

# CORS - allow all for mobile access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(scan.router, prefix="/api/best-buy")
app.include_router(suppliers.router, prefix="/api/best-buy")
app.include_router(products.router, prefix="/api/best-buy")
app.include_router(orders.router, prefix="/api/best-buy")
app.include_router(receiving.router, prefix="/api/best-buy")
app.include_router(cart.router, prefix="/api/best-buy")

# Static files for frontend - check multiple locations
FRONTEND_DIRS = [
    Path(__file__).parent.parent / "best_buy_frontend",  # Local dev
    Path(__file__).parent.parent / "static",  # Render deployment
    Path(__file__).parent / "frontend",  # Alternative
]

FRONTEND_DIR = None
for d in FRONTEND_DIRS:
    if d.exists():
        FRONTEND_DIR = d
        app.mount("/static", StaticFiles(directory=d), name="static")
        break


@app.get("/")
@app.get("/index.html")
async def root():
    """Serve the scanner app or show API info."""
    if FRONTEND_DIR:
        scanner_file = FRONTEND_DIR / "index.html"
        if scanner_file.exists():
            return FileResponse(scanner_file)
    return {
        "app": "Best Buy Scanner",
        "version": "1.0.0",
        "docs": "/docs",
        "scanner": "/static/index.html"
    }


@app.get("/orders.html")
async def orders_page():
    """Serve the orders page."""
    if FRONTEND_DIR:
        orders_file = FRONTEND_DIR / "orders.html"
        if orders_file.exists():
            return FileResponse(orders_file)
    return {"error": "Orders page not found"}


@app.get("/receiving.html")
async def receiving_page():
    """Serve the receiving page."""
    if FRONTEND_DIR:
        receiving_file = FRONTEND_DIR / "receiving.html"
        if receiving_file.exists():
            return FileResponse(receiving_file)
    return {"error": "Receiving page not found"}


@app.get("/scanner.html")
async def scanner_page():
    """Serve the Best Buy scanner page."""
    if FRONTEND_DIR:
        scanner_file = FRONTEND_DIR / "scanner.html"
        if scanner_file.exists():
            return FileResponse(scanner_file)
    return {"error": "Scanner page not found"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


def seed_if_empty():
    """Seed database with initial data if empty."""
    from .models import Product, Supplier

    db = SessionLocal()
    try:
        product_count = db.query(Product).count()
        if product_count == 0:
            print("Database empty - seeding initial data...")
            seed_suppliers(db)
            seed_products_from_embedded(db)
            print("Seeding complete!")
        else:
            print(f"Database has {product_count} products")
    finally:
        db.close()


def seed_suppliers(db):
    """Create initial supplier records."""
    from .models import Supplier

    suppliers_data = [
        {"code": "HACKNEY", "name": "HT Hackney", "feed_type": "manual", "min_order_amount": 500, "order_lead_days": 2, "delivery_days": "Mon,Wed,Fri"},
        {"code": "BROCKMAN", "name": "Brockman's", "feed_type": "manual", "min_order_amount": 300, "order_lead_days": 1, "delivery_days": "Mon,Tue,Wed,Thu,Fri"},
        {"code": "MCLANE", "name": "McLane Company", "feed_type": "csv", "min_order_amount": 750, "order_lead_days": 2, "delivery_days": "Tue,Thu"},
        {"code": "COREMARK", "name": "Core-Mark International", "feed_type": "api", "min_order_amount": 500, "order_lead_days": 3, "delivery_days": "Mon,Wed,Fri"},
        {"code": "FRITO", "name": "Frito-Lays", "feed_type": "manual", "min_order_amount": 200, "order_lead_days": 1, "delivery_days": "Mon,Wed,Fri"},
        {"code": "PEPSI", "name": "Pepsi Bottling Group", "feed_type": "manual", "min_order_amount": 200, "order_lead_days": 1, "delivery_days": "Mon,Wed,Fri"},
        {"code": "COKE", "name": "Coca Cola Bottling Co.", "feed_type": "manual", "min_order_amount": 200, "order_lead_days": 1, "delivery_days": "Tue,Thu"},
        {"code": "PRAIRIE", "name": "Prairie Farms", "feed_type": "manual", "min_order_amount": 100, "order_lead_days": 1, "delivery_days": "Mon,Wed,Fri"},
    ]

    for s_data in suppliers_data:
        supplier = Supplier(**s_data, is_active=True)
        db.add(supplier)
    db.commit()
    print(f"Created {len(suppliers_data)} suppliers")


def seed_products_from_embedded(db):
    """Seed products from embedded pricebook data."""
    from .models import Product, SupplierPrice, Supplier
    from datetime import datetime
    import json
    import random

    # Check for pricebook file in multiple locations
    pricebook_paths = [
        Path(__file__).parent.parent / "data" / "pricebook.json",
        Path(__file__).parent / "data" / "pricebook.json",
    ]

    pricebook_path = None
    for p in pricebook_paths:
        if p.exists():
            pricebook_path = p
            break

    if not pricebook_path:
        print("No pricebook.json found - skipping product seed")
        return

    print(f"Loading pricebook from {pricebook_path}...")

    with open(pricebook_path) as f:
        data = json.load(f)

    created = 0
    for item in data["items"]:
        upc = item.get("pos_code", "").strip()
        if not upc:
            continue

        product = Product(
            upc=upc,
            name=item.get("item_name", "")[:255],
            department=item.get("department"),
            current_vendor=item.get("vendor"),
            current_cost=item.get("cost") if item.get("cost") else None,
            retail_price=item.get("price") if item.get("price") else None,
            pack_size=1,
            on_hand=int(item.get("inventory_count") or 0),
            last_synced_at=datetime.now(),
        )
        db.add(product)
        created += 1

        if created % 1000 == 0:
            db.commit()
            print(f"  Processed {created}...")

    db.commit()
    print(f"Created {created} products")

    # Add sample prices for ALL products with a cost
    products = db.query(Product).filter(Product.current_cost.isnot(None)).all()
    suppliers = db.query(Supplier).all()
    print(f"Adding sample prices for {len(products)} products from {len(suppliers)} suppliers...")

    prices_created = 0
    for product in products:
        current_cost = float(product.current_cost) if product.current_cost else 1.00
        # Each product gets prices from 2-4 random suppliers
        num_suppliers = random.randint(2, min(4, len(suppliers)))
        selected_suppliers = random.sample(suppliers, num_suppliers)
        for supplier in selected_suppliers:
            variation = random.uniform(-0.15, 0.10)
            unit_cost = round(current_cost * (1 + variation), 4)
            case_pack = random.choice([6, 12, 24, 36, 48])

            price = SupplierPrice(
                upc=product.upc,
                product_id=product.id,
                supplier_id=supplier.id,
                unit_cost=unit_cost,
                case_cost=round(unit_cost * case_pack, 2),
                case_pack=case_pack,
                effective_date=datetime.now(),
                price_type="list",
                in_stock=True,
                source="seed"
            )
            db.add(price)
            prices_created += 1

        # Commit every 500 prices to avoid memory issues
        if prices_created % 500 == 0:
            db.commit()
            print(f"  Created {prices_created} prices...")

    db.commit()
    print(f"Created {prices_created} sample prices")


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()
    seed_if_empty()
    print("Best Buy Scanner API started")

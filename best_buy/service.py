"""
Best Buy Service - Core price comparison engine.
Adapted from Lighthouse best_buy_service.py for retail items.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from .models import Product, Supplier, SupplierPrice, UPCAlias, SupplierShipping, BestBuyComparison
from . import schemas


class BestBuyService:
    """
    Core price comparison engine for retail items.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_best_prices_for_upc(
        self,
        upc: str,
        max_age_hours: int = 168,  # 7 days for retail
        include_out_of_stock: bool = False,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get ranked supplier prices for a UPC.
        Main entry point for scanning.
        """

        # 1. Get product info
        product = self.get_product_by_upc(upc)
        if not product:
            return {
                "upc": upc,
                "product": None,
                "prices": [],
                "statistics": None,
                "suppliers_checked": 0,
                "comparison_time": datetime.now().isoformat(),
                "error": "Product not found in catalog"
            }

        # 2. Get all UPC variants (aliases)
        all_upcs = self.get_upc_variants(upc)

        # 3. Calculate freshness cutoff
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        # 4. Query supplier prices
        query = self.db.query(SupplierPrice).filter(
            SupplierPrice.upc.in_(all_upcs),
            SupplierPrice.effective_date >= cutoff,
            SupplierPrice.effective_date <= datetime.now(),
        )

        # Check expiry
        query = query.filter(
            or_(
                SupplierPrice.expires_at.is_(None),
                SupplierPrice.expires_at > datetime.now()
            )
        )

        # Filter out of stock if requested
        if not include_out_of_stock:
            query = query.filter(SupplierPrice.in_stock == True)

        # Order by supplier and date to get latest per supplier
        query = query.order_by(
            SupplierPrice.supplier_id,
            desc(SupplierPrice.effective_date)
        )

        prices = query.all()

        # 5. Dedupe to latest price per supplier
        seen_suppliers = set()
        unique_prices = []
        for price in prices:
            if price.supplier_id not in seen_suppliers:
                seen_suppliers.add(price.supplier_id)
                unique_prices.append(price)

        # 6. Build results with landed cost
        results = []
        for price in unique_prices:
            supplier = self.db.query(Supplier).get(price.supplier_id)
            if not supplier or not supplier.is_active:
                continue

            shipping = self.get_shipping_cost(price.supplier_id)

            landed_cost = self.calculate_landed_cost(
                unit_cost=float(price.unit_cost),
                case_pack=price.case_pack or 1,
                shipping=shipping
            )

            # Calculate savings vs current
            savings = None
            if product.current_cost:
                savings = float(product.current_cost) - float(price.unit_cost)

            results.append({
                "supplier_id": supplier.id,
                "supplier_name": supplier.name,
                "supplier_code": supplier.code,
                "unit_cost": float(price.unit_cost),
                "case_cost": float(price.case_cost) if price.case_cost else float(price.unit_cost) * (price.case_pack or 1),
                "case_pack": price.case_pack or 1,
                "landed_cost_per_unit": landed_cost,
                "effective_date": price.effective_date.isoformat(),
                "price_age_hours": self.get_price_age_hours(price.effective_date),
                "in_stock": price.in_stock,
                "price_type": price.price_type or "list",
                "promo_name": price.promo_name,
                "savings_vs_current": round(savings, 4) if savings else None,
            })

        # 7. Sort by landed cost
        results.sort(key=lambda x: x["landed_cost_per_unit"])

        # 8. Add rank
        for i, r in enumerate(results):
            r["rank"] = i + 1

        # 9. Calculate statistics
        stats = None
        if results:
            costs = [r["unit_cost"] for r in results]
            potential_savings = None
            if product.current_cost:
                potential_savings = float(product.current_cost) - min(costs)

            stats = {
                "min_cost": min(costs),
                "max_cost": max(costs),
                "avg_cost": round(sum(costs) / len(costs), 4),
                "spread": round(max(costs) - min(costs), 4),
                "potential_savings": round(potential_savings, 4) if potential_savings and potential_savings > 0 else None,
            }

        # 10. Build product info
        product_info = {
            "id": product.id,
            "name": product.name,
            "department": product.department,
            "current_cost": float(product.current_cost) if product.current_cost else None,
            "current_vendor": product.current_vendor,
            "retail_price": float(product.retail_price) if product.retail_price else None,
            "pack_size": product.pack_size or 1,
        }

        return {
            "upc": upc,
            "product": product_info,
            "prices": results[:limit],
            "statistics": stats,
            "suppliers_checked": len(results),
            "comparison_time": datetime.now().isoformat(),
            "error": None
        }

    def get_product_by_upc(self, upc: str) -> Optional[Product]:
        """Get product by UPC."""
        return self.db.query(Product).filter(Product.upc == upc).first()

    def get_upc_variants(self, upc: str) -> List[str]:
        """
        Get all UPC variants including aliases.
        Handles UPC-A (12) vs EAN-13 (13) formats.
        """
        variants = [upc]

        # Check aliases
        aliases = self.db.query(UPCAlias).filter(
            UPCAlias.standard_upc == upc
        ).all()

        for alias in aliases:
            if alias.supplier_sku not in variants:
                variants.append(alias.supplier_sku)

        # UPC format variations
        if len(upc) == 12:
            variants.append("0" + upc)  # EAN-13
        elif len(upc) == 13 and upc.startswith("0"):
            variants.append(upc[1:])  # UPC-A

        return variants

    def get_shipping_cost(self, supplier_id: int) -> Optional[Dict]:
        """Get shipping cost config for supplier."""
        shipping = self.db.query(SupplierShipping).filter(
            SupplierShipping.supplier_id == supplier_id
        ).order_by(desc(SupplierShipping.effective_date)).first()

        if not shipping:
            return None

        return {
            "per_case_fee": float(shipping.per_case_fee) if shipping.per_case_fee else None,
            "flat_fee": float(shipping.flat_fee) if shipping.flat_fee else None,
            "free_shipping_threshold": float(shipping.free_shipping_threshold) if shipping.free_shipping_threshold else None,
        }

    def calculate_landed_cost(
        self,
        unit_cost: float,
        case_pack: int,
        shipping: Optional[Dict]
    ) -> float:
        """
        Calculate landed cost per unit including shipping.
        Simplified vs Lighthouse (no freight tables).
        """
        if not shipping:
            return unit_cost

        per_unit_shipping = 0
        if shipping.get("per_case_fee") and case_pack:
            per_unit_shipping = shipping["per_case_fee"] / case_pack

        return round(unit_cost + per_unit_shipping, 4)

    def get_price_age_hours(self, effective_date: datetime) -> float:
        """Calculate price age in hours."""
        delta = datetime.now() - effective_date
        return round(delta.total_seconds() / 3600, 1)

    def save_comparison(
        self,
        upc: str,
        comparison_data: Dict,
        selected_supplier_id: int,
        quantity: int,
        user_id: Optional[str] = None
    ) -> BestBuyComparison:
        """Save a comparison result."""

        product = comparison_data.get("product", {})
        prices = comparison_data.get("prices", [])
        stats = comparison_data.get("statistics", {})

        best_price = prices[0] if prices else None

        comparison = BestBuyComparison(
            upc=upc,
            product_id=product.get("id"),
            scanned_by=user_id,
            current_cost=product.get("current_cost"),
            current_vendor=product.get("current_vendor"),
            best_supplier_id=best_price["supplier_id"] if best_price else None,
            best_unit_cost=best_price["unit_cost"] if best_price else None,
            savings_per_unit=stats.get("potential_savings") if stats else None,
            all_options=comparison_data,
            action="saved",
            ordered_from_supplier_id=selected_supplier_id,
            order_qty=quantity,
        )

        self.db.add(comparison)
        self.db.commit()
        self.db.refresh(comparison)

        return comparison

    def add_supplier_price(
        self,
        upc: str,
        supplier_id: int,
        unit_cost: float,
        case_cost: Optional[float] = None,
        case_pack: int = 1,
        price_type: str = "list",
        promo_name: Optional[str] = None,
        in_stock: bool = True,
        supplier_sku: Optional[str] = None,
        effective_date: Optional[datetime] = None
    ) -> SupplierPrice:
        """Add a new supplier price."""

        # Link to product if exists
        product = self.get_product_by_upc(upc)
        product_id = product.id if product else None

        price = SupplierPrice(
            upc=upc,
            product_id=product_id,
            supplier_id=supplier_id,
            supplier_sku=supplier_sku,
            unit_cost=unit_cost,
            case_cost=case_cost or (unit_cost * case_pack),
            case_pack=case_pack,
            effective_date=effective_date or datetime.now(),
            price_type=price_type,
            promo_name=promo_name,
            in_stock=in_stock,
            source="manual"
        )

        self.db.add(price)
        self.db.commit()
        self.db.refresh(price)

        return price

    def get_all_suppliers(self, active_only: bool = True) -> List[Supplier]:
        """Get all suppliers."""
        query = self.db.query(Supplier)
        if active_only:
            query = query.filter(Supplier.is_active == True)
        return query.order_by(Supplier.name).all()

    def get_supplier(self, supplier_id: int) -> Optional[Supplier]:
        """Get supplier by ID."""
        return self.db.query(Supplier).get(supplier_id)

    def get_supplier_prices(
        self,
        supplier_id: int,
        department: Optional[str] = None,
        limit: int = 100
    ) -> List[SupplierPrice]:
        """Get all prices from a supplier."""
        query = self.db.query(SupplierPrice).filter(
            SupplierPrice.supplier_id == supplier_id
        )

        if department:
            query = query.join(Product).filter(Product.department == department)

        return query.order_by(desc(SupplierPrice.effective_date)).limit(limit).all()

    def batch_compare(self, upcs: List[str]) -> Dict[str, Any]:
        """Compare multiple UPCs at once."""
        results = []
        total_savings = 0

        for upc in upcs:
            comparison = self.get_best_prices_for_upc(upc)
            results.append(comparison)

            if comparison.get("statistics", {}).get("potential_savings"):
                total_savings += comparison["statistics"]["potential_savings"]

        return {
            "comparisons": results,
            "summary": {
                "items_compared": len(results),
                "items_with_prices": len([r for r in results if r.get("prices")]),
                "total_potential_savings": round(total_savings, 2),
            }
        }

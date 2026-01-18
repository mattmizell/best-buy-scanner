# Best Buy Scanner

Mobile price comparison tool for retail convenience stores.

Scan item barcodes to find the best wholesale prices across suppliers.

## Quick Start

```bash
pip install -r requirements.txt
uvicorn best_buy.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 on your phone to scan items.

## API Endpoints

- `GET /` - Scanner UI
- `GET /api/best-buy/scan/{upc}` - Price comparison for UPC
- `GET /api/best-buy/suppliers` - List suppliers
- `GET /api/best-buy/products` - List products
- `GET /docs` - API documentation

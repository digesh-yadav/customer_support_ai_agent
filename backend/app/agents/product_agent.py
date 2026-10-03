"""Agent 3 - Product Agent: price, stock, warranty, returnability."""
import re
from datetime import timedelta

from .. import db
from ..config import LOW_STOCK_THRESHOLD, RETURN_WINDOW_DAYS
from ..db import today
from .base import AgentResult


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_products(text: str, limit: int = 3) -> list[dict]:
    prods = db.q("SELECT * FROM products")
    nt = _norm(text)
    exact = [p for p in prods if _norm(p["product_name"]) in nt]
    if exact:
        return exact[:limit]
    toks = set(re.findall(r"[a-z0-9]+", text.lower()))
    loose = [p for p in prods if _norm(p["product_name"].split()[-1]) in {_norm(t) for t in toks}]
    return loose[:limit]


def stock_label(qty: int) -> str:
    return "out of stock" if qty == 0 else "low stock" if qty < LOW_STOCK_THRESHOLD else "in stock"


def describe(p: dict, order: dict | None = None) -> dict:
    d = {
        "product_id": p["product_id"], "name": p["product_name"], "price": p["price"],
        "stock": p["stock_quantity"], "stock_label": stock_label(p["stock_quantity"]),
        "warranty_months": p["warranty_months"], "returnable": bool(p["returnable"]),
    }
    # Order-specific answers (warranty end / return window) when an order is in context
    if order and order["status"] == "Delivered" and order.get("expected_delivery"):
        from datetime import date
        delivered = date.fromisoformat(order["expected_delivery"])  # dataset has no delivered_at
        d["warranty_until"] = str(delivered + timedelta(days=30 * p["warranty_months"]))
        left = RETURN_WINDOW_DAYS - (today() - delivered).days
        d["return_window_left"] = max(left, 0)
        d["return_eligible"] = bool(p["returnable"]) and left > 0
    return d


def run(text: str, product_query: str | None, order: dict | None) -> AgentResult:
    found = find_products(product_query or text)
    # No product named but an order is in context -> use the order's items
    if not found and order:
        found = [{"product_id": i["product_id"], "product_name": i["product_name"],
                  "price": i["unit_price"], "warranty_months": i["warranty_months"],
                  "returnable": i["returnable"],
                  "stock_quantity": db.q("SELECT stock_quantity s FROM products WHERE product_id=?",
                                         (i["product_id"],))[0]["s"]} for i in order["items"]]
    if not found:
        return AgentResult("Product Agent", False, {"products": []}, "no matching product")
    items = [describe(p, order) for p in found]
    return AgentResult("Product Agent", True, {"products": items},
                       ", ".join(f"{i['name']} (₹{i['price']:.0f}, {i['stock_label']})" for i in items))

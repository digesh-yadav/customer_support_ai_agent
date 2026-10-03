"""Agent 1 - Order Agent: status, tracking, delivery, details, cancellation.
Only ever touches orders that belong to the logged-in customer."""
from datetime import date

from .. import db
from ..db import today
from .base import AgentResult

ACTIVE = ("Confirmed", "Processing", "Shipped", "Out for Delivery")
DISPATCHED = ("Shipped", "Out for Delivery", "Delivered")


def _fmt(d):
    return date.fromisoformat(d) if d else None


def get_order(order_id: str, customer_id: str) -> dict | None:
    rows = db.q("SELECT * FROM orders WHERE order_id=? AND customer_id=?", (order_id, customer_id))
    if not rows:
        return None
    o = rows[0]
    o["items"] = db.q(
        """SELECT oi.product_id, p.product_name, oi.quantity, oi.unit_price, p.warranty_months, p.returnable
           FROM order_items oi JOIN products p USING(product_id) WHERE oi.order_id=?""",
        (order_id,),
    )
    o["cancellable"] = bool(o["cancellable"])
    for it in o["items"]:
        it["returnable"] = bool(it["returnable"])
    return o


def recent_orders(customer_id: str, n: int = 5) -> list[dict]:
    return db.q(
        "SELECT order_id, status, total_amount, order_date FROM orders WHERE customer_id=? "
        "ORDER BY order_date DESC LIMIT ?", (customer_id, n))


def analyze(o: dict) -> dict:
    """Derive delay + data-consistency anomalies from raw order fields."""
    exp = _fmt(o["expected_delivery"])
    days_late = 0
    if exp and o["status"] in ACTIVE and today() > exp:
        days_late = (today() - exp).days
    anomalies = []
    if o["payment_status"] == "Failed" and o["status"] in DISPATCHED:
        anomalies.append("payment failed but the order was dispatched")
    if o["payment_status"] == "Refunded" and o["status"] in ACTIVE + ("Delivered",):
        anomalies.append("payment shows refunded but the order is still active/delivered")
    if o["payment_status"] == "Pending" and o["status"] == "Delivered":
        anomalies.append("order delivered but payment still pending")
    return {"days_late": days_late, "anomalies": anomalies}


def cancel_eligibility(o: dict) -> tuple[bool, str]:
    if o["status"] == "Cancelled":
        return False, "this order is already cancelled"
    if o["status"] in ("Shipped", "Out for Delivery"):
        return False, f"it is already {o['status'].lower()}, so it can no longer be cancelled (you can refuse delivery or request a return once it arrives)"
    if o["status"] in ("Delivered", "Return Requested", "Refunded"):
        return False, f"it is already {o['status'].lower()}"
    if not o["cancellable"]:
        return False, "it is flagged as non-cancellable"
    return True, "eligible"


def run(customer_id: str, order_id: str | None) -> AgentResult:
    if not order_id:
        recent = recent_orders(customer_id)
        return AgentResult("Order Agent", True, {"order": None, "recent": recent},
                           f"no order id given - found {len(recent)} recent orders")
    o = get_order(order_id, customer_id)
    if not o:
        return AgentResult("Order Agent", False, {"order": None, "not_found": order_id},
                           f"{order_id} not found on this account")
    a = analyze(o)
    ok, why = cancel_eligibility(o)
    o.update(a)
    o["can_cancel"], o["cancel_reason"] = ok, why
    s = f"{order_id}: {o['status']}, payment {o['payment_status']}"
    if a["days_late"]:
        s += f", {a['days_late']}d late"
    if a["anomalies"]:
        s += f", ANOMALY x{len(a['anomalies'])}"
    return AgentResult("Order Agent", True, {"order": o}, s)


def cancel(customer_id: str, order_id: str) -> dict:
    """Write action. Re-verifies eligibility at execution time."""
    o = get_order(order_id, customer_id)
    if not o:
        return {"done": False, "reason": "order not found"}
    ok, why = cancel_eligibility(o)
    if not ok:
        return {"done": False, "reason": why}
    refund = o["payment_status"] == "Paid"
    new_pay = "Refunded" if refund else o["payment_status"]
    db.execute("UPDATE orders SET status='Cancelled', cancellable=0, payment_status=? WHERE order_id=?",
               (new_pay, order_id))
    db.log(customer_id, "Order Agent", "cancel_order", order_id)
    return {"done": True, "refund_initiated": refund, "amount": o["total_amount"]}

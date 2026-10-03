import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["DB_PATH"] = "/tmp/test_support.db"
from app import db, pipeline
db.init_db(force=True)


def pick(sql):
    return db.q(sql)[0]


def test_order_status_only_own_orders():
    o = pick("SELECT order_id, customer_id FROM orders WHERE status='Shipped'")
    other = pick(f"SELECT customer_id FROM customers WHERE customer_id!='{o['customer_id']}'")["customer_id"]
    ok = pipeline.handle(o["customer_id"], f"where is {o['order_id']}")
    assert "Shipped" in ok["reply"]
    leak = pipeline.handle(other, f"where is {o['order_id']}")
    assert "couldn't find" in leak["reply"] and "Shipped" not in leak["reply"]


def test_cancel_needs_confirmation_then_executes():
    o = pick("SELECT order_id, customer_id FROM orders WHERE status='Confirmed' AND payment_status IN ('Paid','Pending') LIMIT 1")
    r1 = pipeline.handle(o["customer_id"], f"cancel {o['order_id']}")
    assert r1["decision"] == "confirm_cancel"
    r2 = pipeline.handle(o["customer_id"], "yes")
    assert "cancelled" in r2["reply"].lower()
    assert pick(f"SELECT status FROM orders WHERE order_id='{o['order_id']}'")["status"] == "Cancelled"


def test_cannot_cancel_shipped():
    o = pick("SELECT order_id, customer_id FROM orders WHERE status='Shipped' AND payment_status='Paid' LIMIT 1")
    r = pipeline.handle(o["customer_id"], f"cancel {o['order_id']}")
    assert r["decision"] == "answer" and "can't cancel" in r["reply"]


def test_product_query():
    c = pick("SELECT customer_id FROM customers")["customer_id"]
    r = pipeline.handle(c, "price and warranty of the smart watch?")
    assert "Smart Watch" in r["reply"] and "1,499" in r["reply"]


def test_human_request_escalates():
    c = pick("SELECT customer_id FROM customers")["customer_id"]
    r = pipeline.handle(c, "I want to talk to a human")
    assert r["decision"] == "escalate" and r["handoff"]["ticket_id"].startswith("TKT")


def test_complaint_creates_ticket_and_dedupes():
    o = pick("SELECT order_id, customer_id FROM orders WHERE status='Delivered' AND payment_status='Paid' LIMIT 1")
    r1 = pipeline.handle(o["customer_id"], f"{o['order_id']} arrived damaged")
    assert r1["decision"] in ("create_ticket", "escalate")
    if r1["decision"] == "create_ticket":
        r2 = pipeline.handle(o["customer_id"], f"{o['order_id']} arrived damaged")
        assert "already have an open ticket" in r2["reply"]


def test_anomaly_escalates():
    o = pick("SELECT order_id, customer_id FROM orders WHERE payment_status='Failed' AND status='Delivered' LIMIT 1")
    r = pipeline.handle(o["customer_id"], f"status of {o['order_id']}")
    assert r["decision"] == "escalate"


def test_cards_and_suggestions_returned():
    o = pick("SELECT order_id, customer_id FROM orders WHERE status='Processing' AND payment_status='Paid' LIMIT 1")
    r = pipeline.handle(o["customer_id"], f"where is {o['order_id']}")
    assert r["cards"][0]["type"] == "order" and r["cards"][0]["progress"] == 1
    assert "Cancel it" in r["suggestions"]


def test_checking_tickets_does_not_create_one():
    c = pick("SELECT customer_id FROM customers")["customer_id"]
    before = pick("SELECT COUNT(*) n FROM support_tickets")["n"]
    r = pipeline.handle(c, "Check my tickets")
    assert r["decision"] == "answer"
    assert pick("SELECT COUNT(*) n FROM support_tickets")["n"] == before
    r2 = pipeline.handle(c, "please raise a ticket, my refund is missing")
    assert r2["decision"] in ("create_ticket", "escalate")

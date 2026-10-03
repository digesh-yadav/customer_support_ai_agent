"""Agent 2 - Support Agent: ticket creation, status, classification, escalation signals."""
from datetime import date

from .. import db
from ..config import SLA_DAYS
from ..db import today
from .base import AgentResult

ISSUE_KEYWORDS = {
    "Damaged product": ["damaged", "broken", "cracked", "defective", "not working", "faulty", "dead on arrival"],
    "Wrong item": ["wrong item", "wrong product", "different item", "not what i ordered", "incorrect item"],
    "Missing item": ["missing", "not in the box", "incomplete", "item not received", "part missing"],
    "Refund pending": ["refund", "money back", "not refunded"],
    "Payment issue": ["payment", "charged twice", "deducted", "double charged", "transaction"],
    "Delivery complaint": ["late", "delay", "not delivered", "hasn't arrived", "not arrived", "delivery"],
    "Account issue": ["account", "login", "password", "email change", "profile"],
}
DEFAULT_PRIORITY = {"Payment issue": "high", "Damaged product": "high", "Wrong item": "high",
                    "Missing item": "high", "Refund pending": "medium", "Delivery complaint": "medium",
                    "Account issue": "low", "General complaint": "low"}
ORDER = ["low", "medium", "high", "urgent"]


def classify(text: str, angry: bool = False, tier: str = "standard", hint: str | None = None) -> dict:
    t = text.lower()
    issue = hint if hint in DEFAULT_PRIORITY else next(
        (k for k, kws in ISSUE_KEYWORDS.items() if any(w in t for w in kws)), "General complaint")
    pri = DEFAULT_PRIORITY[issue]
    bump = int(angry) + int(tier == "premium")
    pri = ORDER[min(ORDER.index(pri) + bump, 3)]
    return {"issue_type": issue, "priority": pri}


def list_tickets(customer_id: str) -> list[dict]:
    rows = db.q("SELECT * FROM support_tickets WHERE customer_id=? ORDER BY created_at DESC", (customer_id,))
    for r in rows:
        age = (today() - date.fromisoformat(r["created_at"])).days
        r["age_days"] = age
        r["sla_breached"] = r["status"] in ("open", "in_progress") and age > SLA_DAYS[r["priority"]]
    return rows


def get_ticket(ticket_id: str, customer_id: str) -> dict | None:
    return next((t for t in list_tickets(customer_id) if t["ticket_id"] == ticket_id), None)


def create_ticket(customer_id: str, order_id: str | None, issue_type: str, description: str,
                  priority: str, assigned_to: str = "AI_AGENT", status: str = "open") -> dict:
    # De-duplicate: same customer + order + issue still open -> reuse it
    dup = db.q("""SELECT * FROM support_tickets WHERE customer_id=? AND issue_type=?
                  AND IFNULL(order_id,'')=IFNULL(?, '') AND status IN ('open','in_progress','waiting_for_customer')""",
               (customer_id, issue_type, order_id))
    if dup:
        return {**dup[0], "duplicate": True}
    n = db.q("SELECT MAX(CAST(SUBSTR(ticket_id,4) AS INTEGER)) m FROM support_tickets")[0]["m"] + 1
    tid = f"TKT{n:05d}"
    db.execute("INSERT INTO support_tickets VALUES (?,?,?,?,?,?,?,?,?)",
               (tid, customer_id, order_id, issue_type, description[:300], priority, status,
                assigned_to, str(today())))
    db.log(customer_id, "Support Agent", "create_ticket", tid)
    return {"ticket_id": tid, "issue_type": issue_type, "priority": priority, "status": status,
            "assigned_to": assigned_to, "order_id": order_id, "duplicate": False}


def run(customer_id: str, text: str, plan: dict, tier: str) -> AgentResult:
    tickets = list_tickets(customer_id)
    cls = classify(text, plan.get("angry", False), tier, plan.get("issue_type"))
    ref = None
    if plan.get("ticket_id"):
        ref = next((t for t in tickets if t["ticket_id"] == plan["ticket_id"]), None)
    open_n = sum(t["status"] in ("open", "in_progress") for t in tickets)
    s = f"class={cls['issue_type']}/{cls['priority']}, {open_n} open tickets"
    if plan.get("ticket_id"):
        s += f", {plan['ticket_id']} " + (ref["status"] if ref else "not found")
    return AgentResult("Support Agent", True,
                       {"classification": cls, "tickets": tickets[:5], "ticket": ref,
                        "ticket_not_found": plan.get("ticket_id") if plan.get("ticket_id") and not ref else None,
                        "open_count": open_n}, s)

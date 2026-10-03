"""Agent 4 - Resolution Agent (decision agent): merges what the other agents found,
applies business rules, picks the next step, and writes the customer reply."""
from .. import llm

ESCALATE_AT_OPEN_TICKETS = 3


def decide(plan: dict, res: dict, customer: dict) -> dict:
    """Pure rule engine -> {action, reasons, ...}. Actions:
    answer | clarify | confirm_cancel | create_ticket | escalate"""
    order = (res.get("order") or {}).get("data", {}).get("order")
    order_missing = bool(res.get("order")) and plan.get("order_id") and not order
    sup = (res.get("support") or {}).get("data", {})
    reasons: list[str] = []

    # --- escalation rules (highest priority) ---
    if plan["wants_human"]:
        reasons.append("customer explicitly asked for a human")
    if plan["angry"]:
        reasons.append("customer is upset / legal or fraud language detected")
    if order and order["anomalies"]:
        reasons += [f"data inconsistency: {a}" for a in order["anomalies"]]
    if sup.get("ticket") and sup["ticket"]["sla_breached"]:
        t = sup["ticket"]
        reasons.append(f"ticket {t['ticket_id']} breached its {t['priority']} SLA ({t['age_days']} days old)")
    if plan["wants_ticket"] and sup.get("open_count", 0) >= ESCALATE_AT_OPEN_TICKETS:
        reasons.append(f"customer already has {sup['open_count']} unresolved tickets")
    if reasons:
        return {"action": "escalate", "reasons": reasons}

    # --- cancellation ---
    if plan["wants_cancel"]:
        if not order:
            return {"action": "clarify", "reasons": ["cancellation needs a valid order id"]}
        if order["can_cancel"]:
            return {"action": "confirm_cancel", "reasons": ["order is cancellable"]}
        return {"action": "answer", "reasons": [f"cancel refused: {order['cancel_reason']}"]}

    # --- complaint -> ticket ---
    if plan["wants_ticket"] and not plan.get("ticket_id"):
        return {"action": "create_ticket", "reasons": ["customer reported a problem"]}

    # --- needs an order but none identified ---
    if "order" in plan["intents"] and not order:
        return {"action": "clarify", "reasons": ["no order identified"]}

    if not plan["intents"]:
        return {"action": "clarify", "reasons": ["intent unclear"]}
    return {"action": "answer", "reasons": ["informational request"]}


# ---------------- reply composition ----------------
def _inr(x) -> str:
    return f"₹{float(x):,.0f}"


def facts(plan, res, decision, outcome, customer) -> list[str]:
    """Structured, verified facts. The LLM may only rephrase these; the fallback prints them."""
    f: list[str] = []
    od = (res.get("order") or {}).get("data", {})
    o = od.get("order")
    if od.get("not_found"):
        f.append(f"I couldn't find order {od['not_found']} on your account.")
    if o and plan["wants_cancel"]:
        f.append(f"Order {o['order_id']} is currently **{o['status']}** ({_inr(o['total_amount'])}, payment {o['payment_status']}).")
    elif o:
        line = f"Order {o['order_id']} is **{o['status']}** (placed {o['order_date']}, total {_inr(o['total_amount'])}, payment {o['payment_status']} via {o['payment_method']})."
        f.append(line)
        f.append("Items: " + ", ".join(f"{i['quantity']}× {i['product_name']}" for i in o["items"]) + ".")
        if o["tracking_number"]:
            f.append(f"Tracking number: {o['tracking_number']}.")
    if o and not plan["wants_cancel"]:
        if o["status"] in ("Confirmed", "Processing", "Shipped", "Out for Delivery"):
            if o["days_late"]:
                f.append(f"Expected delivery was {o['expected_delivery']} - it is running **{o['days_late']} day(s) late**. Sorry about that.")
            else:
                f.append(f"Expected delivery: {o['expected_delivery']}.")
    elif od.get("recent") and decision["action"] == "clarify":
        f.append("Which order do you mean? Your recent orders: " + "; ".join(
            f"{r['order_id']} ({r['status']}, {r['order_date']})" for r in od["recent"]) + ".")

    pd_ = (res.get("product") or {}).get("data", {}).get("products", [])
    for p in pd_:
        line = f"**{p['name']}**: {_inr(p['price'])}, {p['stock_label']} ({p['stock']} units), {p['warranty_months']}-month warranty, {'returnable' if p['returnable'] else 'not returnable'}."
        if "warranty_until" in p:
            line += f" Warranty valid until {p['warranty_until']}."
            line += (f" Return window: {p['return_window_left']} day(s) left - eligible." if p["return_eligible"]
                     else " Return window has closed." if p["returnable"] else "")
        f.append(line)
    if res.get("product") and not res["product"]["ok"]:
        f.append("I couldn't identify which product you mean - could you give me its name?")

    sd = (res.get("support") or {}).get("data", {})
    if sd.get("ticket"):
        t = sd["ticket"]
        f.append(f"Ticket {t['ticket_id']} ({t['issue_type']}, {t['priority']} priority) is **{t['status']}**, assigned to {t['assigned_to']}, opened {t['created_at']}.")
    elif sd.get("ticket_not_found"):
        f.append(f"I couldn't find ticket {sd['ticket_not_found']} on your account.")
    elif "support" in plan["intents"] and not plan["wants_ticket"] and sd.get("tickets"):
        f.append("Your latest tickets: " + "; ".join(
            f"{t['ticket_id']} {t['issue_type']} - {t['status']}" for t in sd["tickets"][:3]) + ".")

    a = decision["action"]
    if a == "answer" and plan["wants_cancel"] and o:
        f.append(f"I can't cancel it because {o['cancel_reason']}.")
    if a == "confirm_cancel":
        f.append(f"This order can be cancelled. {'A refund of ' + _inr(o['total_amount']) + ' will be started. ' if o['payment_status']=='Paid' else ''}**Reply YES to confirm the cancellation** (or NO to keep it).")
    if outcome.get("cancel"):
        c = outcome["cancel"]
        f.append(f"✅ Order cancelled." + (f" Refund of {_inr(c['amount'])} has been initiated (5-7 business days)." if c.get("refund_initiated") else "")
                 if c["done"] else f"I couldn't cancel it: {c['reason']}.")
    if outcome.get("ticket"):
        t = outcome["ticket"]
        f.append((f"You already have an open ticket **{t['ticket_id']}** for this ({t['status']}), so I've kept it instead of opening a duplicate."
                  if t.get("duplicate") else
                  f"🎫 I've created ticket **{t['ticket_id']}** ({t['issue_type']}, {t['priority']} priority). Our team will follow up."))
    if outcome.get("handoff"):
        p = outcome["handoff"]
        f.append(f"🙋 I've handed this to a human specialist ({p['assigned_to']}) under ticket **{p['ticket_id']}** with your full history, so you won't need to repeat yourself.")
    if a == "clarify" and not f:
        f.append("Could you share your order ID (e.g. ORD00012), ticket ID, or the product name? I can help with order tracking, cancellations, product info, and support tickets.")
    return f


def compose(fact_list: list[str], user_msg: str, customer_name: str) -> tuple[str, str]:
    """Returns (reply, mode)."""
    text = llm.complete(
        "You are a warm, concise customer-support assistant. Write the reply to the customer using ONLY the "
        "facts provided - never invent order data, dates, prices or policies. Keep every fact that matters "
        "(ids, dates, amounts, next steps). Keep **bold** markers. Max ~120 words. No greetings longer than a few words.",
        f"Customer ({customer_name}) wrote: {user_msg}\n\nVerified facts:\n- " + "\n- ".join(fact_list), 400)
    if text:
        return text, "llm"
    return "\n".join(fact_list), "template"

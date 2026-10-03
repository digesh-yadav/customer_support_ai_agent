"""The multi-agent pipeline:
USER -> Orchestrator -> [Order | Support | Product] -> Resolution -> (Handoff) -> reply"""
import time

from . import db
from .agents import (handoff_agent, order_agent, orchestrator, product_agent,
                     resolution_agent, support_agent)

SESSIONS: dict[str, dict] = {}   # in-memory per-customer state (last order, pending confirmation)
PRI = ["low", "medium", "high", "urgent"]

STEPS = ["Confirmed", "Processing", "Shipped", "Out for Delivery", "Delivered"]


def _order_card(o: dict) -> dict:
    return {"type": "order", "order_id": o["order_id"], "status": o["status"],
            "payment_status": o["payment_status"], "payment_method": o["payment_method"],
            "total": o["total_amount"], "order_date": o["order_date"],
            "expected_delivery": o["expected_delivery"], "tracking": o["tracking_number"],
            "days_late": o.get("days_late", 0),
            "items": [{"name": i["product_name"], "qty": i["quantity"], "price": i["unit_price"]} for i in o["items"]],
            "steps": STEPS, "progress": STEPS.index(o["status"]) if o["status"] in STEPS else -1}


def _build_cards(res: dict, outcome: dict) -> list[dict]:
    """Structured data the frontend turns into visual cards."""
    cards = []
    o = (res.get("order") or {}).get("data", {}).get("order")
    if o:
        cards.append(_order_card(o))
    for p in (res.get("product") or {}).get("data", {}).get("products", []):
        cards.append({"type": "product", **p})
    sup = (res.get("support") or {}).get("data", {})
    t = outcome.get("ticket") or (None if outcome.get("handoff") else sup.get("ticket"))
    if t:
        cards.append({"type": "ticket", **{k: t.get(k) for k in
                      ("ticket_id", "issue_type", "priority", "status", "assigned_to", "order_id")}})
    if outcome.get("handoff"):
        cards.append({"type": "handoff", **outcome["handoff"]})
    return cards


def _suggest(action: str, order: dict | None, customer_id: str) -> list[str]:
    """Clickable next-step ideas so beginners never face a blank box."""
    if action == "confirm_cancel":
        return ["Yes", "No"]
    if action == "clarify":
        return [f"Where is {r['order_id']}?" for r in order_agent.recent_orders(customer_id, 3)] or ["Show my orders"]
    if order:
        return ["Cancel it", "I have a problem with this order", "Warranty for this order?", "Talk to a human"]
    return ["Show my orders", "Price of Smart Watch", "Check my tickets", "Talk to a human"]


def _step(trace, agent, summary, t0, status="ok"):
    trace.append({"agent": agent, "summary": summary, "status": status,
                  "ms": int((time.perf_counter() - t0) * 1000)})


def handle(customer_id: str, message: str) -> dict:
    cust = db.q("SELECT * FROM customers WHERE customer_id=?", (customer_id,))
    if not cust:
        raise ValueError("unknown customer")
    customer = cust[0]
    session = SESSIONS.setdefault(customer_id, {})
    trace: list[dict] = []

    # ---- 1. Orchestrator ----
    t0 = time.perf_counter()
    plan = orchestrator.route(message, session)
    if plan["order_id"] and "order" not in plan["intents"]:
        plan["intents"].insert(0, "order")
    _step(trace, "Orchestrator", f"[{plan['mode']}] intents={plan['intents'] or ['unclear']}"
          + (f", order={plan['order_id']}" if plan["order_id"] else "")
          + (f", confirm={plan['confirm']}" if plan["confirm"] else ""), t0)

    outcome: dict = {}
    res: dict = {}

    # ---- pending cancellation confirmation (YES / NO) ----
    if plan["confirm"]:
        pend = session.pop("pending")
        t0 = time.perf_counter()
        if plan["confirm"] == "yes":
            outcome["cancel"] = order_agent.cancel(customer_id, pend["order_id"])
            _step(trace, "Order Agent", f"cancel {pend['order_id']} -> {'done' if outcome['cancel']['done'] else outcome['cancel']['reason']}", t0)
            f = resolution_agent.facts({"intents": [], "wants_cancel": False, "wants_ticket": False},
                                       {}, {"action": "answer"}, outcome, customer)
        else:
            f = ["No problem - I've kept your order as it is. Anything else I can help with?"]
        reply, mode = resolution_agent.compose(f, message, customer["name"])
        cards = []
        if plan["confirm"] == "yes":
            o2 = order_agent.get_order(pend["order_id"], customer_id)
            if o2:
                o2.update(order_agent.analyze(o2))
                cards.append(_order_card(o2))
        return {"reply": reply, "trace": trace, "cards": cards, "suggestions": _suggest("answer", None, customer_id),
                "decision": "cancel_executed" if plan["confirm"] == "yes" else "cancel_declined"}

    session.pop("pending", None)

    # ---- 2. Specialist agents (order first: product agent can use its context) ----
    if "order" in plan["intents"]:
        t0 = time.perf_counter()
        r = order_agent.run(customer_id, plan["order_id"])
        res["order"] = {"data": r.data, "ok": r.ok}
        _step(trace, r.agent, r.summary, t0, "ok" if r.ok else "warn")
        if r.data.get("order"):
            session["last_order_id"] = r.data["order"]["order_id"]
    order = (res.get("order") or {}).get("data", {}).get("order")

    if "product" in plan["intents"]:
        t0 = time.perf_counter()
        r = product_agent.run(message, plan.get("product_query"), order)
        res["product"] = {"data": r.data, "ok": r.ok}
        _step(trace, r.agent, r.summary, t0, "ok" if r.ok else "warn")

    if "support" in plan["intents"] or plan["wants_ticket"] or plan["angry"] or plan["wants_human"]:
        t0 = time.perf_counter()
        r = support_agent.run(customer_id, message, plan, customer["customer_tier"])
        res["support"] = {"data": r.data, "ok": r.ok}
        _step(trace, r.agent, r.summary, t0, "ok" if r.ok else "warn")
    cls = (res.get("support") or {}).get("data", {}).get("classification") or \
        support_agent.classify(message, plan["angry"], customer["customer_tier"], plan.get("issue_type"))

    # ---- 3. Resolution (decision) agent ----
    t0 = time.perf_counter()
    decision = resolution_agent.decide(plan, res, customer)
    _step(trace, "Resolution Agent", f"action={decision['action']} | " + "; ".join(decision["reasons"]), t0,
          "escalate" if decision["action"] == "escalate" else "ok")

    # ---- 4. Execute the decision ----
    action = decision["action"]
    if action == "confirm_cancel":
        session["pending"] = {"type": "cancel", "order_id": order["order_id"]}
    elif action == "create_ticket":
        t0 = time.perf_counter()
        oid = order["order_id"] if order else plan["order_id"]
        outcome["ticket"] = support_agent.create_ticket(
            customer_id, oid, cls["issue_type"], f"Customer says: {message[:200]}", cls["priority"])
        _step(trace, "Support Agent", f"ticket {outcome['ticket']['ticket_id']} "
              + ("(existing reused)" if outcome["ticket"].get("duplicate") else "created"), t0)
    elif action == "escalate":
        t0 = time.perf_counter()
        sup = (res.get("support") or {}).get("data", {})
        ref = sup.get("ticket")
        issue = ref["issue_type"] if ref else cls["issue_type"]
        oid = (ref or {}).get("order_id") or (order["order_id"] if order else plan["order_id"])
        pri = cls["priority"] if PRI.index(cls["priority"]) >= 2 else "high"
        ctx = []
        if order:
            ctx.append(f"{order['order_id']}: {order['status']}, payment {order['payment_status']}, expected {order['expected_delivery']}")
        ctx += [f"{t['ticket_id']} {t['issue_type']} ({t['status']})" for t in sup.get("tickets", [])[:3]]
        h = handoff_agent.run(customer, message, oid, decision["reasons"], pri, issue, ctx)
        outcome["handoff"] = h.data["packet"]
        _step(trace, h.agent, h.summary, t0, "escalate")

    # ---- 5. Reply ----
    f = resolution_agent.facts(plan, res, decision, outcome, customer)
    reply, mode = resolution_agent.compose(f, message, customer["name"])
    trace.append({"agent": "Resolution Agent", "summary": f"reply written ({mode})", "status": "ok", "ms": 0})
    return {"reply": reply, "trace": trace, "decision": action, "handoff": outcome.get("handoff"),
            "cards": _build_cards(res, outcome), "suggestions": _suggest(action, order, customer_id)}

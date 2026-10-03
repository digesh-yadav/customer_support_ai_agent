"""Orchestrator: understands the message and decides WHICH agents to call.
Uses Groq when an API key is set; otherwise a rule-based router. IDs are always
extracted by regex (never trusted from the LLM)."""
import re

from .. import llm

ANGRY = ["angry", "worst", "terrible", "unacceptable", "fraud", "scam", "cheat", "legal",
         "lawyer", "sue ", "consumer court", "furious", "disgusting", "pathetic", "useless"]
HUMAN = ["human", "real person", "live agent", "talk to someone", "speak to", "manager", "supervisor", "representative"]
CANCEL = ["cancel"]
ORDER_KW = ["order", "track", "delivery", "deliver", "shipped", "shipping", "where is", "status", "arrive", "package", "eta"]
PRODUCT_KW = ["price", "cost", "stock", "available", "warranty", "return", "returnable", "replace", "how much", "in stock"]
SUPPORT_KW = ["ticket", "complaint", "complain", "issue", "problem", "refund", "damaged", "broken", "wrong item",
              "missing", "escalate", "not working", "defective", "charged", "payment"]
YES = {"yes", "y", "yeah", "yep", "confirm", "confirmed", "sure", "ok", "okay", "proceed", "do it", "go ahead", "yes please"}
NO = {"no", "n", "nope", "don't", "dont", "stop", "never mind", "nevermind"}

SYSTEM = """You are the router of a customer-support multi-agent system. Read the customer message and output JSON:
{"intents": ["order"|"support"|"product"|"human", ...],   // every agent that should run
 "wants_cancel": bool,        // customer wants to cancel an order
 "wants_ticket": bool,        // customer is reporting a problem / asks to raise or escalate a ticket
 "issue_type": one of ["Damaged product","Wrong item","Missing item","Refund pending","Payment issue","Delivery complaint","Account issue","General complaint",null],
 "product_query": string|null, // product the customer asks about
 "wants_human": bool, "angry": bool}
Use "order" for order status/tracking/delivery/details/cancellation, "support" for tickets/complaints/refunds,
"product" for price/stock/warranty/returns of products. Several intents are allowed."""


def _has(t: str, words: list[str]) -> bool:
    return any(w in t for w in words)


def _is_ticket_lookup(t: str) -> bool:
    """'check my tickets', 'status of TKT00012' -> look up only, never create a new ticket."""
    if re.search(r"tkt\d{5}", t):
        return True
    creating = re.search(r"\b(raise|create|open|new|file|log|register)\b", t)
    viewing = re.search(r"\b(check|show|view|list|status|see|track|my tickets)\b", t)
    return bool("ticket" in t and viewing and not creating)


def _rules(text: str) -> dict:
    t = text.lower()
    wants_cancel = _has(t, CANCEL)
    wants_human = _has(t, HUMAN)
    intents = []
    if _has(t, ORDER_KW) or wants_cancel or re.search(r"ord\d{5}", t):
        intents.append("order")
    if _has(t, SUPPORT_KW) or re.search(r"tkt\d{5}", t):
        intents.append("support")
    if _has(t, PRODUCT_KW):
        intents.append("product")
    if wants_human:
        intents.append("human")
    return {"intents": intents, "wants_cancel": wants_cancel,
            "wants_ticket": _has(t, SUPPORT_KW) and not _is_ticket_lookup(t),
            "issue_type": None, "product_query": None, "wants_human": wants_human, "angry": _has(t, ANGRY)}


def route(text: str, session: dict) -> dict:
    t = text.strip().lower().rstrip(".!")
    plan = {"mode": "rules", "confirm": None}
    if session.get("pending"):
        if t in YES:
            return {**plan, "confirm": "yes", "intents": [], "wants_cancel": False, "wants_ticket": False,
                    "wants_human": False, "angry": False, "issue_type": None, "product_query": None,
                    "order_id": None, "ticket_id": None}
        if t in NO:
            return {**plan, "confirm": "no", "intents": [], "wants_cancel": False, "wants_ticket": False,
                    "wants_human": False, "angry": False, "issue_type": None, "product_query": None,
                    "order_id": None, "ticket_id": None}

    base = _rules(text)
    ai = llm.complete_json(SYSTEM, text) if llm.available() else None
    if ai:
        plan["mode"] = "llm"
        for k in ("wants_cancel", "wants_ticket", "wants_human", "angry"):
            base[k] = bool(ai.get(k, base[k])) or (k in ("wants_human", "angry") and base[k])
        base["intents"] = [i for i in ai.get("intents", []) if i in ("order", "support", "product", "human")] or base["intents"]
        base["issue_type"] = ai.get("issue_type")
        base["product_query"] = ai.get("product_query")
    plan.update(base)

    oid = re.search(r"ORD\d{5}", text, re.I)
    tid = re.search(r"TKT\d{5}", text, re.I)
    plan["order_id"] = oid.group(0).upper() if oid else None
    plan["ticket_id"] = tid.group(0).upper() if tid else None
    # "cancel it" / "where is my order" -> reuse the order from earlier in the chat
    if not plan["order_id"] and session.get("last_order_id") and "order" in plan["intents"] \
            and re.search(r"\b(it|that|this|same|my order)\b", t):
        plan["order_id"] = session["last_order_id"]
    if plan["wants_human"] and "human" not in plan["intents"]:
        plan["intents"].append("human")
    if plan["wants_cancel"] and "order" not in plan["intents"]:
        plan["intents"].append("order")
    if plan["wants_ticket"] and "support" not in plan["intents"]:
        plan["intents"].append("support")
    return plan

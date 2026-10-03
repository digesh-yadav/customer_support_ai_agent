"""Agent 5 - Human Handoff Agent: packages the full context and assigns a human."""
from .. import db
from ..config import HUMAN_AGENTS
from . import support_agent
from .base import AgentResult


def _least_loaded() -> str:
    load = {a: 0 for a in HUMAN_AGENTS}
    for r in db.q("SELECT assigned_to, COUNT(*) c FROM support_tickets "
                  "WHERE status IN ('open','in_progress') GROUP BY assigned_to"):
        if r["assigned_to"] in load:
            load[r["assigned_to"]] = r["c"]
    return min(load, key=load.get)


def run(customer: dict, message: str, order_id: str | None, reasons: list[str],
        priority: str, issue_type: str, context_lines: list[str]) -> AgentResult:
    agent = _least_loaded()
    summary = (f"[ESCALATED] {issue_type}. Customer says: \"{message[:140]}\". "
               f"Why escalated: {'; '.join(reasons)}.")
    ticket = support_agent.create_ticket(customer["customer_id"], order_id, issue_type, summary,
                                         priority, assigned_to=agent)
    if ticket.get("duplicate"):
        # Escalate the EXISTING ticket instead of opening a second one
        db.execute("UPDATE support_tickets SET assigned_to=?, priority='urgent', "
                   "description='[ESCALATED] ' || description WHERE ticket_id=?", (agent, ticket["ticket_id"]))
        ticket.update(assigned_to=agent, priority="urgent")
        db.log(customer["customer_id"], "Handoff Agent", "escalate_existing", f"{ticket['ticket_id']} -> {agent}")
    else:
        db.log(customer["customer_id"], "Handoff Agent", "escalate", f"{ticket['ticket_id']} -> {agent}")
    packet = {
        "ticket_id": ticket["ticket_id"], "assigned_to": ticket["assigned_to"], "priority": ticket["priority"],
        "customer": f"{customer['name']} ({customer['customer_tier']}, {customer['city']})",
        "order_id": order_id, "reasons": reasons, "context": context_lines,
        "reused_existing": ticket.get("duplicate", False),
    }
    return AgentResult("Handoff Agent", True, {"packet": packet},
                       f"{ticket['ticket_id']} -> {ticket['assigned_to']} ({ticket['priority']})")

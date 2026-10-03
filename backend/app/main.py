"""Backend API only (no HTML here). The frontend lives in ../frontend and talks to these endpoints."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, llm, pipeline
from .agents import order_agent, support_agent

app = FastAPI(title="Multi-Agent Customer Support API")

# CORS lets the frontend (a different port, e.g. :5500) call this API (:8000)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db.init_db()


class ChatIn(BaseModel):
    customer_id: str
    message: str


@app.get("/")
def root():
    return {"service": "multi-agent-support", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.available()}


@app.get("/api/customers")
def customers():
    return db.q("SELECT customer_id, name, customer_tier, city FROM customers ORDER BY customer_id")


@app.get("/api/customers/{cid}/overview")
def overview(cid: str):
    if not db.q("SELECT 1 FROM customers WHERE customer_id=?", (cid,)):
        raise HTTPException(404, "customer not found")
    return {"orders": order_agent.recent_orders(cid, 6),
            "tickets": [{k: t[k] for k in ("ticket_id", "issue_type", "status", "priority")}
                        for t in support_agent.list_tickets(cid)[:4]]}


@app.post("/api/chat")
def chat(body: ChatIn):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    try:
        return pipeline.handle(body.customer_id, body.message.strip()[:1000])
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/reset")
def reset():
    db.init_db(force=True)
    pipeline.SESSIONS.clear()
    return {"ok": True}

"""SQLite layer. Loads the CSVs on first run so there is zero setup.
(The schema mirrors ai_agent_dataset.sql, so you can swap in PostgreSQL later.)"""
import csv
import sqlite3
from datetime import date

from .config import AS_OF_DATE, DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE customers (customer_id TEXT PRIMARY KEY, name TEXT, email TEXT, phone TEXT,
  city TEXT, state TEXT, pincode TEXT, customer_tier TEXT, created_at TEXT);
CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT, category TEXT,
  price REAL, stock_quantity INTEGER, warranty_months INTEGER, returnable INTEGER);
CREATE TABLE orders (order_id TEXT PRIMARY KEY, customer_id TEXT, status TEXT,
  total_amount REAL, payment_status TEXT, payment_method TEXT, order_date TEXT,
  expected_delivery TEXT, cancellable INTEGER, tracking_number TEXT);
CREATE TABLE order_items (order_item_id TEXT PRIMARY KEY, order_id TEXT, product_id TEXT,
  quantity INTEGER, unit_price REAL);
CREATE TABLE support_tickets (ticket_id TEXT PRIMARY KEY, customer_id TEXT, order_id TEXT,
  issue_type TEXT, description TEXT, priority TEXT, status TEXT, assigned_to TEXT,
  created_at TEXT);
CREATE TABLE agent_log (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT,
  agent TEXT, action TEXT, detail TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP);
"""
LOAD_ORDER = ["customers", "products", "orders", "order_items", "support_tickets"]
BOOL_COLS = {"returnable", "cancellable"}


def today() -> date:
    return date.fromisoformat(AS_OF_DATE) if AS_OF_DATE else date.today()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force: bool = False) -> None:
    if DB_PATH.exists() and not force:
        return
    DB_PATH.unlink(missing_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    for table in LOAD_ORDER:
        with open(DATA_DIR / f"{table}.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        cols = list(rows[0].keys())
        data = []
        for r in rows:
            data.append([
                (1 if r[c].lower() == "true" else 0) if c in BOOL_COLS
                else (r[c] if r[c] != "" else None)
                for c in cols
            ])
        conn.executemany(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", data
        )
    conn.commit()
    conn.close()


def q(sql: str, params: tuple = ()) -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> None:
    conn = connect()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def log(customer_id: str, agent: str, action: str, detail: str = "") -> None:
    execute(
        "INSERT INTO agent_log (customer_id, agent, action, detail) VALUES (?,?,?,?)",
        (customer_id, agent, action, detail),
    )

# Multi-Agent Customer Support System

This project is a small multi-agent customer support application. It connects a simple HTML/CSS/JavaScript frontend with a FastAPI backend, a SQLite database, and an optional Groq LLM.

The idea is simple: a customer sends a message such as **"Where is my order?"**, **"I want a refund"**, or **"I want to talk to a human"**. The backend decides which agent should handle the request and then returns one clear response to the frontend.

## What the project does

- Tracks orders and shows order details
- Handles order cancellation with confirmation
- Answers product price, stock, warranty, and return questions
- Checks and creates support tickets
- Handles customer complaints
- Escalates difficult or human-requested cases
- Uses rule-based routing when no LLM key is configured
- Uses Groq for LLM-powered routing and reply generation when enabled
- Shows the agent flow in the frontend

## Project structure

```text
botivate/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── base.py
│   │   │   ├── handoff_agent.py
│   │   │   ├── orchestrator.py
│   │   │   ├── order_agent.py
│   │   │   ├── product_agent.py
│   │   │   ├── resolution_agent.py
│   │   │   └── support_agent.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── llm.py
│   │   ├── main.py
│   │   └── pipeline.py
│   ├── data/
│   └── tests/
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── resource/
├── api/
│   └── index.py          # Vercel serverless entrypoint
├── vercel.json
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## How it works

```text
Customer
   ↓
Frontend (HTML/CSS/JavaScript)
   ↓
FastAPI /api/chat
   ↓
Orchestrator Agent
   ↓
┌──────────────┬───────────────┬───────────────┐
│ Order Agent  │ Support Agent │ Product Agent │
└──────────────┴───────────────┴───────────────┘
   ↓
Resolution Agent
   ↓
Human Handoff Agent (when needed)
   ↓
Final response + cards + agent trace
   ↓
Frontend
```

The Orchestrator understands the customer's request and decides which specialist agents need to run. The Resolution Agent combines their results and prepares the final response.

## Requirements

- Python 3.10 or newer
- A modern web browser
- A Groq API key is optional

## Backend setup

From the project root, create a virtual environment:

```bash
python -m venv .venv
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Start the backend:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

The API will run at `http://localhost:8000`.

FastAPI documentation is available at `http://localhost:8000/docs`.

## Groq setup

Groq is optional. If you do not provide an API key, the application falls back to its built-in rule-based logic.

The easiest way is to copy the example file and fill it in (`backend/.env` is git-ignored):

```bash
cp backend/.env.example backend/.env
```

Or set the variable in your shell:

Windows PowerShell:

```powershell
$env:GROQ_API_KEY="your_groq_api_key"
```

The project currently uses this default model setting:

```text
openai/gpt-oss-20b
```

You can change it with:

```powershell
$env:LLM_MODEL="openai/gpt-oss-20b"
```

After setting the variables, restart the backend.

You can check the LLM status at:

```text
http://localhost:8000/api/health
```

If `llm` is `true`, Groq is active.

## Frontend setup

The frontend is plain HTML, CSS, and JavaScript, so Node.js and npm are not required.

After starting the backend, open `frontend/index.html` in your browser.

The frontend currently connects to:

```javascript
const API_BASE = "http://localhost:8000";
```

This setting is in `frontend/js/config.js` (and inline in `frontend/index.html`). On `localhost` it points to port 8000; when deployed it automatically uses the same origin, so no change is needed for Vercel.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Basic service information |
| GET | `/api/health` | Checks backend and LLM status |
| GET | `/api/customers` | Returns available customers |
| GET | `/api/customers/{cid}/overview` | Gets customer orders and tickets |
| POST | `/api/chat` | Sends a customer message to the agent pipeline |
| POST | `/api/reset` | Restores the demo database |

Example `/api/chat` request:

```json
{
  "customer_id": "CUS00001",
  "message": "Where is my order?"
}
```

## Database

The project uses SQLite, so there is no need to install MySQL or PostgreSQL for this demo. The CSV files in `backend/data/` are used to initialize the local database.

The database path can be changed with the `DB_PATH` environment variable.

## Running tests

From the project root:

```bash
pip install -r requirements-dev.txt
pytest backend/tests -v
```

The tests check things such as order ownership, cancellation confirmation, product queries, ticket creation, escalation, duplicate tickets, and data anomalies.

## Useful environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | empty | Enables Groq |
| `LLM_MODEL` | `openai/gpt-oss-20b` | Groq model used by the app |
| `DB_PATH` | `backend/support.db` | SQLite database location |
| `AS_OF_DATE` | `2026-09-29` | Date used for deterministic demo data |
| `RETURN_WINDOW_DAYS` | `10` | Return-policy window |

## Try these messages

```text
Where is my order?
Cancel my order
Price and warranty of Smart Watch
Is Running Shoes in stock?
My order arrived damaged
Check my tickets
I want to talk to a human
```

## Deploy on Vercel

The repo is already configured: `vercel.json` serves `frontend/` as the static site and routes `/api/*` to the FastAPI app via `api/index.py`.

1. Push this repo to GitHub (see below).
2. Go to [vercel.com/new](https://vercel.com/new) and import the repository.
3. Leave the framework preset as **Other**. Do not override the build settings.
4. Under **Environment Variables**, add (all optional):
   - `GROQ_API_KEY` - your Groq key
   - `LLM_MODEL` - e.g. `openai/gpt-oss-20b`
   - `AS_OF_DATE` - e.g. `2026-09-29`
   - `RETURN_WINDOW_DAYS` - e.g. `10`
5. Click **Deploy**, then open `https://<your-app>.vercel.app/api/health`.

> **Demo-data note:** Vercel functions have a read-only filesystem and no persistent memory. The app rebuilds its SQLite database from `backend/data/*.csv` into `/tmp` on cold start, so changes (cancellations, new tickets) and chat sessions are not guaranteed to persist between requests. This is fine for a demo; for production use a hosted database (Postgres, Turso, etc.) and external session storage.

## Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/botivate.git
git push -u origin main
```

Before the first commit, run `git status` and confirm `.env` and `.venv/` are **not** listed.

## Why this project is useful

This project is mainly a learning and internship-style demonstration of a multi-agent support system. It keeps the architecture understandable: the frontend sends a request, FastAPI receives it, the Orchestrator selects the required agents, the database provides the information, and the Resolution Agent prepares the final answer.

For a production application, I would add authentication, proper user sessions, a production database, stricter CORS rules, rate limiting, logging, monitoring, and secure secret management.

## Troubleshooting

### Frontend says the backend is offline

Make sure the backend is running:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Then check `frontend/js/config.js` and make sure `API_BASE` points to the same backend address.

### Groq is not being used

Make sure `GROQ_API_KEY` is set in the same terminal from which you start the backend. Then open `/api/health` and check that `llm` is `true`.

### Reset the demo data

Use the reset option in the frontend or send a `POST` request to `/api/reset`.



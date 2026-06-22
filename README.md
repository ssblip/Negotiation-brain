# Negotiation Brain

A two-sided AI negotiation platform. Buyers upload vendor quote documents, set targets, and the AI bot negotiates with each vendor in real time — driven by the Negotiation Brain v3.0 strategy document.

## Architecture

```
React + Vite (port 5173)                       FastAPI (port 8000)
┌─────────────────────────────┐               ┌──────────────────────────────────────┐
│  Buyer Portal               │               │  /api/auth/*                         │
│    My Negotiations          │               │  /api/negotiations/*  (buyer)        │
│    New Negotiation wizard   │ ── REST ────▶ │  /api/vendor/*        (vendor acct)  │
│    Live table + chat view   │               │  /api/negotiate/{token}  (magic link) │
│  Vendor Portal              │               │  Claude API (negotiation engine)     │
│    My Bids dashboard        │               │  SQLite DB                           │
│    AI negotiation chat      │               └──────────────────────────────────────┘
└─────────────────────────────┘
```

## Key Features

| Feature | Detail |
|---|---|
| Quote parsing | Single PDF/Excel/Word doc → AI extracts all vendors |
| Scoring | Spec Score (0-100) + CVS across price/delivery/payment/warranty |
| Strategy auto-select | S1–S6 per Negotiation Brain v3.0 decision tree |
| AI negotiation | Claude follows the strategy doc — zero internal number leakage |
| Vendor auth | Full accounts (email+password) + magic-link fallback |
| Live monitoring | Buyer table polls every 5s, Export to Excel |
| Escalation | Bot alerts buyer when above reservation price or impasse |
| Vendor memory | Persistent archetype profile per vendor email |

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

## Environment Variables (backend/.env)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `JWT_SECRET` | Long random string for JWT signing |
| `SMTP_HOST/PORT/USER/PASS` | Email provider settings |
| `FRONTEND_URL` | Used in vendor invitation links |
| `CLAUDE_MODEL` | Default: `claude-sonnet-4-6` |
| `MAX_ROUNDS` | Max negotiation rounds before BAFO (default: 8) |

## Workflow

1. **Buyer** registers → creates negotiation
2. Uploads **strategy doc** (NegotiationBrain_v3_COMPLETE.docx) → becomes AI's system prompt
3. Uploads **vendor quotes doc** (PDF/Excel with all vendors) → AI parses it
4. Reviews extracted vendors, adds emails, sets negotiation targets
5. Clicks **Send Invitations** → emails each vendor
6. **Vendor** registers/logs in → sees negotiation in dashboard
7. Opens chat → AI bot greets them, negotiates using strategy doc
8. **Buyer** monitors the live table (auto-refreshes every 5s)
9. Escalations appear as alerts → buyer decides proceed/accept/reject
10. Agreement reached → buyer gets email, reviews, accepts

## File Map

```
backend/app/
  main.py          — All FastAPI routes
  models.py        — SQLAlchemy models
  schemas.py       — Pydantic request/response types
  auth.py          — JWT + bcrypt
  config.py        — Settings from .env
  database.py      — SQLAlchemy engine
  parser.py        — PDF/Excel/Word → text → Claude extraction
  scorer.py        — Spec Score, CVS, strategy selection (S1-S6)
  negotiation.py   — Claude negotiation engine + state machine
  emailer.py       — Vendor invitation + escalation emails

frontend/src/
  App.tsx                        — Router + nav + auth guard
  api.ts                         — Typed API client
  pages/
    LoginPage.tsx / RegisterPage.tsx
    BuyerDashboard.tsx           — Negotiation list
    NewNegotiationPage.tsx       — 5-step wizard
    NegotiationDetailPage.tsx    — Live table + chat viewer + escalations
    VendorDashboard.tsx          — Vendor's bid history
    VendorChatPage.tsx           — AI chat (token or account mode)
```

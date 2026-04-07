# Clarobill

AI-powered medical bill error detection. Analyzes itemized bills for duplicate charges, upcoding, and NCCI unbundling violations. Generates plain-English reports and dispute letters.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | Python FastAPI |
| Database | PostgreSQL via Supabase |
| Auth | Supabase Auth (magic link) |
| OCR | Google Cloud Vision API |
| AI Analysis | Anthropic Claude API |
| Payments | Stripe Checkout |
| File Storage | Supabase Storage (encrypted) |
| Email | SendGrid |
| Error Monitoring | Sentry |
| Analytics | PostHog |
| Frontend Hosting | Vercel |
| Backend Hosting | Railway |

## Project Structure

```
clarobill/
├── apps/
│   ├── web/                 # Next.js frontend
│   └── engine/              # Python FastAPI billing analysis service
├── packages/
│   └── shared/              # Shared TypeScript types
├── supabase/
│   └── migrations/          # SQL migration files
├── scripts/                 # CMS data refresh scripts
└── railway.json             # Railway deployment config
```

## Local Development

### Prerequisites

- Node.js 20+
- Python 3.11+
- A Supabase project
- API keys for: Anthropic, Google Cloud Vision, Stripe, SendGrid

### Frontend

```bash
cd apps/web
cp .env.example .env.local   # fill in your keys
npm install
npm run dev                  # http://localhost:3000
```

### Engine

```bash
cd apps/engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env         # fill in your keys
uvicorn app.main:app --reload --port 8000
```

### Environment Variables

See `apps/web/.env.example` and `apps/engine/.env.example` for the full list of required variables.

## Deployment

- **Frontend** → Vercel (root directory: `apps/web`)
- **Engine** → Railway (uses `railway.json` + `apps/engine/Dockerfile`)

## License

Proprietary. © Flow Financial Group. All rights reserved.

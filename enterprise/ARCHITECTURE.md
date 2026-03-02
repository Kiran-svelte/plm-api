# PLM ENTERPRISE - Architecture Document
# Building a Competitor to Claude/OpenAI with BETTER Niche Models

## Vision

**PLM (Private Language Models) - The OpenAI for Niche Expertise**

Instead of one general model, we provide:
- **100+ specialized expert models** (healthcare, legal, finance, crypto, etc.)
- **Better than Claude/OpenAI** in specific domains
- **No hallucination** (fact-checked, RAG-enhanced)
- **Continuously learning** from customer usage
- **100% automated** (zero human intervention)
- **Fully auditable** (compliance-ready)

---

## Competitive Advantage vs Claude/OpenAI

| Feature | Claude/OpenAI | PLM Enterprise |
|---------|---------------|----------------|
| **Expertise** | General (jack of all trades) | Niche expert (master of one) |
| **Hallucination** | High (no fact-checking) | Low (RAG + fact-check layer) |
| **Privacy** | Cloud (data sent to them) | Private (runs on customer infra) |
| **Learning** | Static (can't learn from you) | Adaptive (learns from your usage) |
| **Context** | Limited (200k tokens) | Unlimited (RAG retrieval) |
| **Cost** | $50-500/month forever | $1,500 one-time |
| **Compliance** | Hard (third-party) | Easy (on-premise) |
| **Accountability** | None | Full audit trail |

---

## Solving the 7 AI Gaps

### Gap 1: Hallucination - AI Confidently Lies
**Our Solution:**
```
User Query
    ↓
1. Model generates answer
    ↓
2. RAG retrieves facts from knowledge base
    ↓
3. Fact-checker validates claims
    ↓
4. Confidence scorer rates answer
    ↓
5. If confidence < 80%, flag for review
    ↓
6. Return answer with confidence score
```

**Implementation:**
- Knowledge graph per niche
- Fact database with sources
- Multi-model verification (3 models vote)
- Citation requirements
- Confidence thresholds

### Gap 2: No Real Understanding
**Our Solution:**
- Domain ontologies (structured knowledge)
- Expert validation during training
- Reasoning chains (show work)
- Test suites per domain
- Human expert review for edge cases

### Gap 3: Training Data Cutoff
**Our Solution:**
```
Continuous Learning Pipeline:
1. Customer uses model
2. Queries logged (with permission)
3. Answers validated by customer
4. Good answers → added to training
5. Model retrained weekly
6. Deployed automatically
```

### Gap 4: Can't Learn On The Job
**Our Solution:**
- Per-customer memory (Supabase vector DB)
- Context accumulation
- Customer-specific fine-tuning
- Usage pattern learning
- Automatic improvement

### Gap 5: Reasoning Breaks on Novel Problems
**Our Solution:**
- Chain-of-thought prompting
- Multi-step reasoning
- Sub-problem decomposition
- External tool calling (calculators, APIs)
- Human escalation for truly novel problems

### Gap 6: No Accountability
**Our Solution:**
- Full audit logs (Supabase)
- Answer provenance (sources tracked)
- Version control on models
- Human-in-loop options
- Legal compliance features

### Gap 7: Context Window Limits
**Our Solution:**
- RAG system (unlimited retrieval)
- Summarization cascade
- Document chunking
- Intelligent context selection
- Multi-turn conversation memory

---

## Enterprise Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CUSTOMER LAYER                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Web Portal  │  │  Mobile App  │  │  REST API    │     │
│  │  (Next.js)   │  │  (React)     │  │  (Public)    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
└─────────┼──────────────────┼──────────────────┼────────────┘
          │                  │                  │
          └──────────────────┴──────────────────┘
                             │
          ┌──────────────────▼─────────────────────┐
          │         CLOUDFLARE CDN                 │
          │    (DDoS Protection, Caching)          │
          └──────────────────┬─────────────────────┘
                             │
          ┌──────────────────▼─────────────────────┐
          │         LOAD BALANCER                  │
          │    (Nginx / Render)                    │
          └──────────────────┬─────────────────────┘
                             │
          ┌──────────────────┴─────────────────────┐
          │                                        │
┌─────────▼──────────┐              ┌──────────▼──────────┐
│   FRONTEND         │              │   BACKEND           │
│   (Vercel)         │              │   (Render)          │
│                    │              │                     │
│ - Next.js 14      │              │ - FastAPI           │
│ - React 18        │              │ - Python 3.11       │
│ - TypeScript      │              │ - Redis Queue       │
│ - Shadcn UI       │              │ - Celery Workers    │
│ - TailwindCSS     │              │ - WebSockets        │
└────────┬───────────┘              └──────────┬──────────┘
         │                                     │
         │          ┌──────────────────────────┤
         │          │                          │
         │          │                          │
┌────────▼──────────▼─────────────────────────▼──────────┐
│                  SUPABASE                               │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ PostgreSQL   │  │ Auth         │  │ Storage      │ │
│  │ (Main DB)    │  │ (Users)      │  │ (Files)      │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Vector DB    │  │ Real-time    │  │ Edge Funcs   │ │
│  │ (RAG)        │  │ (WebSocket)  │  │ (Serverless) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                             │
          ┌──────────────────┴─────────────────────┐
          │                                        │
┌─────────▼──────────┐              ┌──────────▼──────────┐
│ MODEL TRAINING     │              │ MODEL SERVING       │
│ (Render Workers)   │              │ (Render + Ollama)   │
│                    │              │                     │
│ - Data Gen         │              │ - Model API         │
│ - Quality Check    │              │ - RAG System        │
│ - Model Training   │              │ - Fact Checker      │
│ - Deployment       │              │ - Confidence Score  │
└────────┬───────────┘              └──────────┬──────────┘
         │                                     │
         └──────────────────┬──────────────────┘
                            │
          ┌─────────────────▼──────────────────┐
          │       MONITORING & LOGGING         │
          │                                    │
          │ - Sentry (Error tracking)         │
          │ - Logflare (Logs)                 │
          │ - Prometheus (Metrics)            │
          │ - Grafana (Dashboards)            │
          └────────────────────────────────────┘
```

---

## Technology Stack

### Frontend
- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript
- **UI:** Shadcn UI + TailwindCSS
- **State:** Zustand
- **API Client:** React Query
- **Auth:** Supabase Auth
- **Hosting:** Vercel

### Backend
- **API:** FastAPI (Python 3.11)
- **Workers:** Celery
- **Queue:** Redis
- **WebSockets:** Socket.io
- **Hosting:** Render

### Database & Storage
- **Database:** Supabase (PostgreSQL 15)
- **Vector DB:** pgvector (for RAG)
- **Cache:** Redis
- **File Storage:** Supabase Storage
- **Backup:** Automated daily snapshots

### AI/ML
- **Training:** Hugging Face Transformers
- **Base Models:** Llama 3.2, Mistral
- **Fine-tuning:** LoRA/QLoRA
- **Inference:** Ollama + vLLM
- **RAG:** LangChain + pgvector
- **Embeddings:** sentence-transformers

### Infrastructure
- **CDN:** Cloudflare
- **DNS:** Cloudflare
- **Containers:** Docker
- **Orchestration:** Docker Compose
- **CI/CD:** GitHub Actions
- **Monitoring:** Sentry + Prometheus

### Security
- **Auth:** Supabase Auth (JWT)
- **API Security:** Rate limiting, CORS
- **Encryption:** TLS 1.3, AES-256
- **Secrets:** Environment variables
- **Compliance:** SOC 2, GDPR ready

---

## Database Schema (Supabase)

```sql
-- Organizations (Customers)
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  niche TEXT NOT NULL,
  tier TEXT NOT NULL, -- starter, professional, enterprise
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB
);

-- Users
CREATE TABLE users (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  organization_id UUID REFERENCES organizations(id),
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL, -- owner, admin, member
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Models
CREATE TABLE models (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id),
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL, -- training, ready, deployed
  base_model TEXT NOT NULL,
  metrics JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Training Data
CREATE TABLE training_data (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id),
  instruction TEXT NOT NULL,
  output TEXT NOT NULL,
  metadata JSONB,
  quality_score FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Knowledge Base (for RAG)
CREATE TABLE knowledge_base (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id),
  content TEXT NOT NULL,
  embedding VECTOR(768), -- pgvector
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Queries (for learning)
CREATE TABLE queries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id),
  model_id UUID REFERENCES models(id),
  query TEXT NOT NULL,
  response TEXT NOT NULL,
  confidence FLOAT,
  feedback TEXT, -- good, bad, excellent
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fact Checks
CREATE TABLE fact_checks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  query_id UUID REFERENCES queries(id),
  claim TEXT NOT NULL,
  verified BOOLEAN,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Logs
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id),
  user_id UUID REFERENCES users(id),
  action TEXT NOT NULL,
  details JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_training_data_org ON training_data(organization_id);
CREATE INDEX idx_queries_org ON queries(organization_id);
CREATE INDEX idx_knowledge_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops);
```

---

## Automated Pipeline

```
CUSTOMER SIGNS UP
       ↓
[Supabase Auth] → Create org in DB
       ↓
[Backend API] → Create workspace
       ↓
[Worker 1: Data Generation]
  - Generate 1000 Q&A pairs
  - Quality check each
  - Store in training_data table
       ↓
[Worker 2: Knowledge Base]
  - Extract facts
  - Generate embeddings
  - Store in knowledge_base table
       ↓
[Worker 3: Model Training]
  - Load base model
  - Fine-tune on customer data
  - Validate on test set
  - Store model in storage
       ↓
[Worker 4: Deployment]
  - Deploy model to Ollama
  - Create API endpoint
  - Update model status → ready
       ↓
[Customer Portal]
  - Notify customer
  - Model ready to use
       ↓
[Continuous Learning]
  - Log queries
  - Collect feedback
  - Retrain weekly
  - Auto-deploy updates
```

---

## Next Steps

Building:
1. Supabase database setup
2. Backend APIs (FastAPI)
3. Frontend portal (Next.js)
4. Automated training pipeline
5. RAG implementation
6. Fact-checking system
7. CI/CD pipeline
8. Docker containers
9. Production deployment

---

**This is the architecture for a REAL competitor to Claude/OpenAI!**

---

## v2.0 Additions

### New System: Pet Personality Engine

Each organization's model now has a living AI pet personality that evolves through 6 stages based on real training metrics:

**Egg 🥚 → Hatchling 🐣 → Juvenile 🐥 → Adult 🦅 → Master 🦁 → Legend 🐉**

- Stage and mood are computed from `training_data` count and `models.metrics.accuracy`
- XP tracks cumulative model growth
- Personality modifies the system prompt automatically
- See `enterprise/pet_personality.py` and `PLM_V2_ARCHITECTURE.md`

### New Solution for Privacy Gap: Privacy Proxy

Addresses a new critical gap: **user data leaking to external AI providers**.

| Gap | Problem | Solution |
|-----|---------|----------|
| **Privacy** | Queries to Groq/Gemini may contain PII | `PrivacyProxy` strips emails, phones, SSNs, IPs, company names before every external API call |

The Privacy Proxy (`enterprise/privacy_proxy.py`) is integrated into `generate_answer_with_context()` and is **on by default** for all new queries. Extra-strict rules apply to training data generation.

### New System: Multi-Modal Router

Extends PLM beyond text-only:

| Modality | Use Case | Specialized Model |
|----------|----------|-------------------|
| Text | Standard Q&A | Groq (default) |
| Code | Generation & review | DeepSeek-R1 (Groq) + Qwen2.5 (SambaNova) |
| Image | Visual analysis | Groq (text description) |
| Voice | TTS narration | Groq (optimized for speech) |

All modalities share the same RAG knowledge base and niche system prompt.
See `enterprise/modality_router.py`, `enterprise/code_service.py`, `PLM_V2_ARCHITECTURE.md`.

### Updated Competitive Advantage Table

| Feature | Claude/OpenAI | PLM v1 | PLM v2.0 |
|---------|---------------|--------|---------|
| **Expertise** | General | Niche expert | Niche expert + evolving pet |
| **Hallucination** | High | Low (RAG+FC) | Low (RAG+FC+Privacy) |
| **Privacy** | Cloud (data sent to them) | Private infra | Private infra + PII proxy |
| **Learning** | Static | Adaptive | Adaptive + personality |
| **Modalities** | Text + image | Text only | Text + Code + Image + Voice |
| **Compliance** | Hard | Full audit | Full audit + privacy audit |


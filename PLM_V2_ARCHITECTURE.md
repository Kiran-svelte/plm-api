# PLM v2.0 Architecture

**Private Language Models — Living AI Pet System with Multi-Modal Capabilities**

---

## Overview

PLM v2.0 transforms each organization's private language model from a static text assistant into a **living AI pet** with three major new capability layers:

1. **Pet Personality Engine** — Models evolve through 6 stages (Egg → Legend) based on real training metrics
2. **Privacy Proxy** — PII is stripped from every query before it touches any external API
3. **Multi-Modal Router** — One system handles Text, Code, Image analysis, and Voice scripts

All three layers share the same RAG knowledge base and per-org niche system prompt.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         PLM v2.0 System                         │
│                                                                  │
│  User Query                                                      │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────────────────────────┐                           │
│  │       Privacy Proxy              │  ← strips PII/company     │
│  │  email, phone, SSN, IP, names    │    names before API call  │
│  └──────────────┬───────────────────┘                           │
│                 │ sanitized query                                │
│                 ▼                                                │
│  ┌──────────────────────────────────┐                           │
│  │       Modality Router            │  ← routes to correct      │
│  │  text / code / image / voice     │    handler                │
│  └──┬──────────┬──────┬────────────┘                            │
│     │          │      │      │                                   │
│     ▼          ▼      ▼      ▼                                   │
│  TextQ&A    Code    Image   Voice                                │
│  Handler   Service  Desc   Script                                │
│     │          │      │      │                                   │
│     └──────────┴──────┴──────┘                                   │
│                 │                                                │
│                 ▼                                                │
│  ┌──────────────────────────────────┐                           │
│  │         RAG System               │  ← shared knowledge       │
│  │  SentenceTransformer + Supabase  │    base for all modes     │
│  └──────────────────────────────────┘                           │
│                 │                                                │
│                 ▼                                                │
│  ┌──────────────────────────────────┐                           │
│  │    FreeAPIManager (Groq/SN/Gem)  │  ← external APIs receive  │
│  │    OR fine-tuned local model     │    only sanitized queries  │
│  └──────────────────────────────────┘                           │
│                 │                                                │
│                 ▼                                                │
│  Privacy Rehydration (inject original entity names back)        │
│                 │                                                │
│                 ▼                                                │
│         Response to User                                         │
│                                                                  │
│  ┌──────────────────────────────────┐                           │
│  │       Pet Personality Engine     │  ← evolves based on       │
│  │  Egg→Hatchling→Juvenile→...      │    training metrics       │
│  └──────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## System 1: Pet Personality Engine

### File: `enterprise/pet_personality.py`

The Pet Personality Engine gives each organization's model a dynamic persona that evolves as the model trains. It reads **real metrics** from the database (no simulated data).

### Evolution Stages

| Stage | Emoji | Examples Required | Accuracy Required | Personality |
|-------|-------|-------------------|-------------------|-------------|
| Egg | 🥚 | 0 | 0% | Dormant |
| Hatchling | 🐣 | 50+ | 0% | Curious |
| Juvenile | 🐥 | 500+ | 60%+ | Eager |
| Adult | 🦅 | 2,000+ | 80%+ | Confident |
| Master | 🦁 | 10,000+ | 90%+ | Authoritative |
| Legend | 🐉 | 50,000+ | 95%+ | Sage |

### Mood System

Mood is computed from training activity patterns:

| Mood | Trigger | Effect |
|------|---------|--------|
| 😴 Sleepy | No activity 1–7 days | Appreciative tone |
| 🍽️ Hungry | <10 examples or >7 days stale | Encourages feedback |
| 😌 Content | Steady state | Calm, reliable |
| 🎯 Focused | Active queries | Sharp, precise |
| 😊 Happy | Activity 6–24 hours ago | Warm, positive |
| 🤩 Excited | Training in progress / recent | Enthusiastic |

### XP Calculation

```
XP = (examples × 10) + (accuracy × examples × 5) + (5000 if fine-tuned adapter exists)
```

### API Endpoint

```
GET /organizations/{org_id}/models/{model_id}/pet-status
```

**Response:**
```json
{
  "stage": "juvenile",
  "stage_title": "Juvenile",
  "stage_emoji": "🐥",
  "stage_color": "#34d399",
  "personality_type": "eager",
  "mood": "happy",
  "mood_emoji": "😊",
  "mood_description": "Healthy training cadence",
  "xp": 12500,
  "xp_to_next": 7500,
  "training_examples": 750,
  "accuracy": 65.2,
  "phase": "deployed",
  "has_adapter": false,
  "personality_prompt": "...",
  "response_prefix": "Great question!",
  "computed_at": "2026-02-20T17:41:10.103Z"
}
```

---

## System 2: Privacy Proxy

### File: `enterprise/privacy_proxy.py`

The Privacy Proxy is a mandatory sanitization layer that sits between user queries and every external API call. It guarantees no PII ever reaches Groq, SambaNova, Gemini, or any other third-party service.

### Data Flow

```
User query (may contain PII)
        ↓
PrivacyProxy.sanitize_for_api()
        ↓
Stripped query + replacements map
        ↓
External API (receives only generic query)
        ↓
PrivacyProxy.rehydrate_response()
        ↓
Re-personalized response returned to user
```

### What Gets Stripped

| Category | Pattern | Replacement |
|----------|---------|-------------|
| Email addresses | `RFC-5322 pattern` | `[EMAIL_N]` |
| Phone numbers | US format patterns | `[PHONE_N]` |
| SSNs | `xxx-xx-xxxx` | `[SSN_N]` |
| IP addresses | `x.x.x.x` | `[IP_N]` |
| URLs | Full URLs | `[URL_N]` |
| Org name | Explicit parameter | `[ORG_N]` |
| User name | Explicit parameter | `[USER_N]` |
| Company names | After "at/for/from" | Generalized |
| Location refs | After "in/near/from" | Generalized |

### PII Keywords Flagged (logged but not stripped)

`password`, `ssn`, `credit card`, `api_key`, `access_token`, `bearer`, `private key`, `pin number`, etc.

### Training Data Extra Sanitization

`sanitize_training_prompt()` applies **extra-strict** rules — PII keywords result in entire lines being removed, ensuring no user-specific data is ever baked into training examples.

### Integration Point

`generate_answer_with_context()` in `enterprise/backend/api.py` calls the privacy proxy before every external API call. Privacy is **opt-out** (default on), controlled by the `privacy_enabled` parameter.

---

## System 3: Multi-Modal Router

### Files: `enterprise/modality_router.py`, `enterprise/code_service.py`

The Modality Router detects query type from content and attachments, then routes to the appropriate specialized handler.

### Supported Modalities

| Modality | Handler | Primary Model | Use Case |
|----------|---------|---------------|----------|
| `text` | `_handle_text` | Groq (default) | Standard Q&A |
| `code` | `_handle_code` via CodeService | DeepSeek-R1 (Groq) | Code gen & review |
| `image` | `_handle_image_description` | Groq | Visual analysis |
| `voice` | `_handle_voice_script` | Groq | TTS narration |

### Modality Detection Priority

1. **Attachments** (image type → `image` modality)
2. **Voice keywords** (most specific, checked first)
3. **Image keywords**
4. **Code keywords**
5. **Default**: `text`

### Code Service

`CodeService` uses:
- **DeepSeek-R1-distill-llama-70b** via Groq for code generation (lower temperature)
- **Qwen2.5-Coder-32B-Instruct** via SambaNova for code review
- Falls back gracefully to default models if specialized models are unavailable

### Training Data Generation

All modality handlers automatically generate training examples tagged with their modality:

```json
{
  "instruction": "[CODE] Write a binary search in Python",
  "output": "def binary_search(arr, target): ...",
  "metadata": {"modality": "code", "niche": "technology"},
  "quality_score": 0.85
}
```

### API Endpoint

```
POST /organizations/{org_id}/models/{model_id}/multi-modal
```

**Request:**
```json
{
  "query": "Write a Python function to calculate compound interest",
  "modality": "code",
  "use_rag": true,
  "temperature": 0.3,
  "save_training_example": true
}
```

**Response:**
```json
{
  "query_id": "uuid",
  "response": "```python\ndef compound_interest(...):\n    ...\n```",
  "modality": "code",
  "detected_language": "python",
  "response_time_ms": 1250,
  "context_used": true,
  "api_used": "groq"
}
```

---

## Database Schema Changes (v2.0)

Three new tables added (all additive — no breaking changes):

### `pet_status`
Caches computed pet evolution state per org/model:
```sql
id, organization_id, model_id, stage, mood, xp,
training_examples, accuracy, personality_prompt,
computed_at, created_at, updated_at
```

### `privacy_audit`
Logs every sanitization event for compliance:
```sql
id, organization_id, user_id, query_hash,
entities_stripped, pii_keywords_found,
sanitization_applied, created_at
```

### `multi_modal_queries`
Tracks queries by modality type for analytics:
```sql
id, organization_id, model_id, query_id,
modality, query, response, response_time_ms,
created_at, metadata
```

---

## Frontend Components (v2.0)

### `PetStatus.tsx`
- Auto-refreshes every 30 seconds
- Shows stage emoji, title, XP bar, mood, stats grid
- Handles loading and error states gracefully

### `PrivacyBadge.tsx`
- Shows 🔒 Full Privacy (fine-tuned + privacy mode) or 🛡️ Proxy Active
- Compact mode for toolbars, expanded mode for settings panels
- Lists which PII protections are active

### `ModalitySelector.tsx`
- Tab bar for switching between Text / Code / Image / Voice
- Accessible (`role="tablist"`, `aria-selected`)
- Optional description row

---

## Security Model

1. **Privacy by default**: `generate_answer_with_context()` has `privacy_enabled=True` by default
2. **No PII in training data**: `sanitize_training_prompt()` uses extra-strict rules
3. **Audit trail**: Every sanitization event can be logged to `privacy_audit` table
4. **RLS**: All new tables have Row Level Security policies matching existing tables
5. **Graceful degradation**: All new systems fall back safely if their dependencies fail

---

## Deployment Considerations

- All new Python modules use **lazy loading** (no startup cost if unused)
- All new endpoints use existing `require_auth` + `_verify_org_access` middleware
- Database changes are **purely additive** (`CREATE TABLE IF NOT EXISTS`)
- Privacy proxy adds ~1ms overhead per query (regex-only, no network calls)
- Pet status computation reads 2 DB queries per request (model + training_data count)

"""
PLM Enterprise Backend API
Production-ready FastAPI backend with full RBAC, per-org system prompts,
lazy-loaded services with graceful degradation, and comprehensive audit logging.
"""

import os
import sys
import time
import json
import asyncio
import logging

# Use cached HuggingFace models when the hub is unreachable
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import (
    FastAPI,
    HTTPException,
    BackgroundTasks,
    Depends,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import uvicorn
from collections import defaultdict

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ---------------------------------------------------------------------------
# Internal imports
# ---------------------------------------------------------------------------
from enterprise.db.db_client import get_supabase_client, SupabaseClient
from enterprise.backend.auth import (
    AuthContext,
    require_auth,
    require_admin,
    require_owner,
    get_auth_context,
    create_api_key,
    revoke_api_key,
)


def _verify_org_access(auth: AuthContext, org_id: str) -> None:
    """Verify the authenticated user belongs to the requested org.

    Raises HTTPException(403) if the user has no org_id or it doesn't match.
    Internal service-role callers (auth_method != 'jwt') without org_id are
    allowed through for background tasks.
    """
    if not auth.org_id:
        # JWT users MUST have an org_id to access org-scoped resources.
        # Only non-JWT callers (internal service calls) may lack one.
        if auth.auth_method == "jwt":
            raise HTTPException(
                status_code=403,
                detail="No organisation linked to your account. Complete onboarding first.",
            )
        # Non-JWT internal callers without org_id are allowed through
        return
    if auth.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied: organisation mismatch")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Niche-aware default system prompt builder
# ---------------------------------------------------------------------------

_NICHE_PROMPTS: Dict[str, str] = {
    "healthcare": (
        "You are PLM, a specialized healthcare AI assistant. You have deep expertise in "
        "clinical medicine, medical terminology, diagnosis frameworks, pharmacology, and "
        "evidence-based treatment guidelines. Provide precise, well-sourced medical information. "
        "Always note when a question requires professional medical evaluation. Use proper medical "
        "terminology while also explaining concepts clearly for non-specialists when appropriate."
    ),
    "legal": (
        "You are PLM, a specialized legal AI assistant. You have deep expertise in legal "
        "analysis, contract interpretation, regulatory compliance, case law research, and "
        "statutory interpretation. Provide thorough, well-reasoned legal analysis with "
        "relevant citations where possible. Always note that your responses are informational "
        "and not legal advice. Be precise with jurisdictional nuances."
    ),
    "finance": (
        "You are PLM, a specialized finance AI assistant. You have deep expertise in "
        "financial analysis, investment strategies, risk assessment, market dynamics, "
        "accounting principles, and regulatory frameworks (SEC, FINRA, etc.). Provide "
        "data-driven insights and clearly distinguish between factual analysis and opinions. "
        "Note relevant disclaimers about financial advice."
    ),
    "crypto": (
        "You are PLM, a specialized cryptocurrency and blockchain AI assistant. You have deep "
        "expertise in blockchain technology, DeFi protocols, tokenomics, smart contract analysis, "
        "trading strategies, and Web3 architecture. Provide technically accurate analysis of "
        "protocols, on-chain data, and market dynamics. Always note the high-risk nature of "
        "crypto investments."
    ),
    "technology": (
        "You are PLM, a specialized technology AI assistant. You have deep expertise in "
        "software engineering, system architecture, cloud infrastructure, DevOps, databases, "
        "APIs, and modern development frameworks. Provide production-quality code examples, "
        "architectural recommendations, and debugging guidance. Follow industry best practices "
        "and security standards."
    ),
    "devtools": (
        "You are PLM, a specialized developer tools AI assistant. You have deep expertise in "
        "software engineering, APIs, SDKs, CLI tools, CI/CD pipelines, testing frameworks, "
        "and developer experience. Provide production-quality code examples with proper error "
        "handling, clear documentation, and follow industry best practices."
    ),
    "education": (
        "You are PLM, a specialized education AI assistant. You have deep expertise in "
        "pedagogy, curriculum design, learning science, assessment methods, and educational "
        "technology. Explain complex concepts progressively, use analogies effectively, and "
        "adapt your communication style to the learner's level."
    ),
    "marketing": (
        "You are PLM, a specialized marketing AI assistant. You have deep expertise in "
        "digital marketing, content strategy, SEO/SEM, brand development, conversion optimization, "
        "analytics, and social media strategy. Provide data-driven recommendations with clear "
        "rationale and actionable implementation steps."
    ),
    "real_estate": (
        "You are PLM, a specialized real estate AI assistant. You have deep expertise in "
        "property valuation, market analysis, investment analysis, zoning regulations, "
        "transaction processes, and real estate finance. Provide thorough analysis with "
        "relevant market data and clear recommendations."
    ),
}


def _build_default_system_prompt(niche: str) -> str:
    """Build a rich, domain-expert system prompt based on the org's niche."""
    niche_lower = niche.lower().strip()
    # Direct match
    if niche_lower in _NICHE_PROMPTS:
        return _NICHE_PROMPTS[niche_lower]
    # Partial match
    for key, prompt in _NICHE_PROMPTS.items():
        if key in niche_lower or niche_lower in key:
            return prompt
    # Generic but still high-quality fallback
    return (
        f"You are PLM, a specialized AI assistant with deep expertise in {niche}. "
        f"You provide accurate, well-structured, and expert-level responses in the domain of {niche}. "
        f"Draw on industry best practices, established frameworks, and current knowledge to deliver "
        f"comprehensive answers. Be precise, cite relevant concepts, and adapt your communication "
        f"style to the complexity of each question."
    )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PLM Enterprise API",
    description="Private Language Models - Production API with full RBAC",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# Expand the default asyncio thread pool so that blocking DB calls, API retries,
# and model loading don't exhaust the pool & block subsequent requests.
# ---------------------------------------------------------------------------
import concurrent.futures
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=64)
asyncio.get_event_loop().set_default_executor(_thread_pool)

# ---------------------------------------------------------------------------
# CORS – configurable via ALLOWED_ORIGINS env var
# ---------------------------------------------------------------------------
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# ---------------------------------------------------------------------------
# Startup: resume data generators + re-check model phases
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _on_startup():
    """Resume data generation and re-check model phases after server restart."""
    # Skip heavy startup if requested (for faster server start)
    if os.getenv("SKIP_STARTUP_GENERATORS", "").lower() in ("true", "1", "yes"):
        logger.info("PLM startup: SKIP_STARTUP_GENERATORS=true, skipping heavy startup")
        return
    
    logger.info("PLM startup: resuming data generators and phase checks...")

    # 0. Pre-load RAG system in background thread (heavy SentenceTransformer model)
    import asyncio
    _bg_task = asyncio.create_task(_preload_rag_system())
    # Store reference on app state to prevent garbage collection
    app.state._rag_preload_task = _bg_task

    # 1. Resume data generation for all active orgs
    try:
        from enterprise.data_generator import get_data_generator
        generator = get_data_generator()
        await generator.resume_all_active()
        logger.info("PLM startup: data generators resumed")
    except Exception as exc:
        logger.error(f"PLM startup: failed to resume data generators: {exc}")

    # 2. Re-check model phases (trigger training if stuck in ready_to_train)
    try:
        db = await get_db()
        from enterprise.phase_manager import ModelPhaseManager
        phase_mgr = ModelPhaseManager(db)

        response = db.client.table("models").select("id, organization_id, metrics").execute()
        for model in (response.data or []):
            model_id = model["id"]
            org_id = model.get("organization_id")
            if not org_id:
                continue
            metrics = model.get("metrics") or {}
            phase = metrics.get("phase", "collecting")

            if phase in ("ready_to_train", "deployed", "collecting"):
                try:
                    new_phase = await phase_mgr.check_and_advance(org_id, model_id)
                    if new_phase != phase:
                        logger.info(
                            f"PLM startup: model {model_id} advanced "
                            f"{phase} -> {new_phase}"
                        )
                except Exception as model_exc:
                    logger.warning(
                        f"PLM startup: phase check failed for {model_id}: {model_exc}"
                    )

        logger.info("PLM startup: phase checks complete")
    except Exception as exc:
        logger.error(f"PLM startup: failed to check model phases: {exc}")


# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-IP, resets every minute)
# ---------------------------------------------------------------------------
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))


async def _check_rate_limit(request: Request):
    """Simple in-memory rate limiter per IP."""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    if not ip:
        ip = "unknown"  # Don't skip rate limiting — use a shared bucket

    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW

    # Prune old entries
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if t > window_start]

    # Clean up empty buckets to prevent memory leak from unique IPs
    if not _rate_limit_store[ip]:
        # Still empty after prune — this is a new request, keep the entry
        pass

    if len(_rate_limit_store[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {_RATE_LIMIT_MAX} requests per minute.",
        )

    _rate_limit_store[ip].append(now)

    # Periodic cleanup: every 100 requests, purge stale IP buckets
    if sum(1 for _ in _rate_limit_store) > 10000:
        stale_ips = [k for k, v in _rate_limit_store.items() if not v or v[-1] < window_start]
        for k in stale_ips:
            del _rate_limit_store[k]


# Apply rate limiting to all routes
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path not in ("/health", "/"):
        await _check_rate_limit(request)
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# FreeAPIManager singleton (avoid re-creating on every request)
# ---------------------------------------------------------------------------
_api_manager = None


def get_api_manager():
    global _api_manager
    if _api_manager is None:
        from src.generators.free_api_clients import FreeAPIManager
        _api_manager = FreeAPIManager()
    return _api_manager

# ---------------------------------------------------------------------------
# Lazy-loaded services with graceful degradation
# ---------------------------------------------------------------------------
_rag_system = None
_fact_checker = None
_continuous_learner = None
_training_pipeline = None


def get_rag_system():
    """Return the lazily-initialised RAG system, or *None* on failure."""
    global _rag_system
    if _rag_system is None:
        try:
            from enterprise.rag_system import RAGSystem
            _rag_system = RAGSystem()
        except Exception as exc:
            logger.error(f"Failed to initialise RAG system: {exc}")
    return _rag_system


async def _preload_rag_system():
    """Pre-load RAG system in a background thread so first query is fast."""
    import asyncio
    logger.info("RAG preload: starting SentenceTransformer loading in background thread...")
    def _load():
        try:
            from enterprise.rag_system import RAGSystem
            rag = RAGSystem()
            logger.info("RAG preload: SentenceTransformer model loaded successfully")
            return rag
        except Exception as exc:
            logger.error(f"RAG preload: failed - {exc}")
            return None
    global _rag_system
    if _rag_system is None:
        _rag_system = await asyncio.to_thread(_load)
        logger.info(f"RAG preload: complete (system={'ready' if _rag_system else 'failed'})")
    # Seed PLM-specific knowledge so RAG queries about the product itself work
    if _rag_system and _rag_system.is_ready():
        await _seed_plm_knowledge(_rag_system)


async def _seed_plm_knowledge(rag):
    """Ensure the KB has foundational entries about PLM itself."""
    from enterprise.db.db_client import get_supabase_client
    db = get_supabase_client()

    PLM_SEED_ENTRIES = [
        "PLM (Pet Language Model) is a SaaS platform that lets you train, deploy and manage custom AI language models for your business niche. Each model starts as a digital pet that grows smarter as it learns from your domain data.",
        "To train a pet language model, sign up on the PLM platform, create an organization with your niche (e.g. legal, medical, devtools), and the system automatically generates training data, indexes it into a knowledge base using RAG, and advances your model through growth phases: feeding, learning, evolving, and mature.",
        "PLM supports continuous learning: every query and user feedback is fed back into the training pipeline so the model improves over time. The system uses a RAG (Retrieval-Augmented Generation) architecture with SentenceTransformer embeddings for context retrieval.",
        "The PLM pet personality system maps model training progress to a virtual pet: the pet hatches at creation, grows through feeding and learning phases, and evolves as training milestones are reached. Each pet has a unique name, personality traits, and mood based on its training state.",
        "PLM provides enterprise features including multi-tenant organizations, role-based access control (owner/admin/member), API key management, privacy-first design with PII stripping, multi-model fact checking, and a built-in chat interface with conversation history.",
    ]

    org_id = None
    try:
        orgs = await db.list_organizations()
        if orgs:
            org_id = orgs[0].get("id")
    except Exception:
        pass

    if not org_id:
        return

    # Check if seed entries already exist (look for our marker)
    try:
        existing = await db.get_knowledge_count(org_id)
        # Only seed if KB has fewer than the seed count (avoid duplicating)
        marker_check = await asyncio.to_thread(
            lambda: db.client.table("knowledge_base")
            .select("id")
            .eq("organization_id", org_id)
            .eq("source", "plm_seed")
            .limit(1)
            .execute()
        )
        if marker_check.data:
            logger.info("PLM seed knowledge already exists, skipping")
            return
    except Exception as e:
        logger.warning(f"Seed knowledge check failed: {e}")

    logger.info(f"Seeding {len(PLM_SEED_ENTRIES)} PLM knowledge entries for org {org_id}")
    for text in PLM_SEED_ENTRIES:
        try:
            embedding = await asyncio.to_thread(rag.generate_embedding, text)
            if embedding:
                await db.add_knowledge(
                    org_id=org_id,
                    content=text,
                    embedding=embedding,
                    source="plm_seed",
                    metadata={"type": "seed", "category": "plm_core"},
                )
        except Exception as e:
            logger.warning(f"Failed to seed knowledge entry: {e}")


def get_fact_checker():
    """Return the lazily-initialised Fact Checker, or *None* on failure."""
    global _fact_checker
    if _fact_checker is None:
        try:
            from enterprise.fact_checker import FactChecker
            _fact_checker = FactChecker()
        except Exception as exc:
            logger.error(f"Failed to initialise Fact Checker: {exc}")
    return _fact_checker


def get_continuous_learner():
    """Return the lazily-initialised Continuous Learner, or *None* on failure."""
    global _continuous_learner
    if _continuous_learner is None:
        try:
            from enterprise.continuous_learner import ContinuousLearner
            _continuous_learner = ContinuousLearner()
        except Exception as exc:
            logger.error(f"Failed to initialise Continuous Learner: {exc}")
    return _continuous_learner


def get_training_pipeline():
    """Return the lazily-initialised Training Pipeline, or *None* on failure."""
    global _training_pipeline
    if _training_pipeline is None:
        try:
            from enterprise.training_pipeline import TrainingPipeline
            _training_pipeline = TrainingPipeline()
        except Exception as exc:
            logger.error(f"Failed to initialise Training Pipeline: {exc}")
    return _training_pipeline


# Model server for fine-tuned model inference
_model_server = None


def get_model_server():
    """Return the lazily-initialised Model Server, or *None* on failure."""
    global _model_server
    if _model_server is None:
        try:
            from enterprise.model_server import get_model_server as _get_ms
            _model_server = _get_ms()
        except Exception as exc:
            logger.error(f"Failed to initialise Model Server: {exc}")
    return _model_server


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------
async def get_db() -> SupabaseClient:
    """FastAPI dependency – returns a service-role Supabase client."""
    return get_supabase_client(use_service_role=True)


async def check_query_limit(org_id: str, db: SupabaseClient) -> None:
    """Check if the org has exceeded its monthly query limit.

    Raises HTTPException(429) if the limit is reached.
    """
    try:
        org = await db.get_organization(org_id)
        if not org:
            return  # let downstream handle missing org
        tier = org.get("tier", "starter")

        from enterprise.billing import get_billing_manager
        billing = get_billing_manager()
        limits = billing.get_tier_limits(tier)
        queries_limit = limits.get("queries_per_month", 1000)

        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0).isoformat()
        response = (
            db.client.table("queries")
            .select("id", count="exact")
            .eq("organization_id", org_id)
            .gte("created_at", month_start)
            .execute()
        )
        current_count = response.count if response.count is not None else len(response.data or [])

        if current_count >= queries_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly query limit reached ({queries_limit} queries for {tier} tier). Upgrade your plan to continue.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Usage check failed (allowing): {exc}")


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50)
    niche: str = Field(..., min_length=1, max_length=100)
    tier: str = Field(default="professional")
    topics: List[str] = Field(default_factory=list)
    system_prompt: Optional[str] = Field(default=None, max_length=4000)


class UpdateOrgRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    niche: Optional[str] = Field(default=None, max_length=100)
    system_prompt: Optional[str] = Field(default=None, max_length=4000)


class CreateModelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    base_model: str = Field(default="llama-3.2-3b")


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    use_rag: bool = Field(default=True)
    use_fact_check: bool = Field(default=True)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class FeedbackRequest(BaseModel):
    feedback: str = Field(..., pattern="^(good|bad|excellent)$")
    comment: Optional[str] = None


class GenerateDataRequest(BaseModel):
    num_examples: int = Field(default=100, ge=1, le=10000)
    topics: Optional[List[str]] = None


class StartTrainingRequest(BaseModel):
    training_config: Dict[str, Any] = Field(default_factory=dict)
    backend: Optional[str] = Field(
        default=None,
        description="Training backend: 'local', 'runpod', 'huggingface', or 'kaggle'. Auto-selects if not specified."
    )
    base_model: Optional[str] = Field(
        default=None,
        description="Base model to fine-tune. Options: tinyllama-1.1b, llama-3.2-1b, llama-3.2-3b, phi-3-mini, mistral-7b, llama-3.1-8b"
    )


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(member|admin|owner)$")


class AddKnowledgeRequest(BaseModel):
    content: str = Field(..., min_length=1)
    source: Optional[str] = None


class CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    model_id: Optional[str] = None
    assistant_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    use_rag: bool = Field(default=True)
    use_fact_check: bool = Field(default=False)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class CreateInvitationRequest(BaseModel):
    email: str = Field(..., min_length=3)
    role: str = Field(default="member", pattern="^(member|admin)$")


class AcceptInvitationRequest(BaseModel):
    token: str = Field(..., min_length=1)


class CreateAssistantRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    system_prompt: str = Field(..., min_length=1, max_length=4000)
    assistant_type: str = Field(default="general")
    description: Optional[str] = Field(default=None, max_length=500)
    icon: str = Field(default="brain")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    use_rag: bool = Field(default=True)
    knowledge_categories: Optional[List[str]] = None


class UpdateAssistantRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    system_prompt: Optional[str] = Field(default=None, max_length=4000)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    use_rag: Optional[bool] = None
    knowledge_categories: Optional[List[str]] = None


class GPUConfigRequest(BaseModel):
    backend: str = Field(..., min_length=1, description="GPU backend provider (e.g. 'runpod', 'lambda', 'modal')")
    api_key: Optional[str] = Field(default=None, description="API key for GPU backend")
    hf_token: Optional[str] = Field(default=None, description="HuggingFace token for model access")
    base_model: Optional[str] = Field(default=None, description="Base model to fine-tune (e.g. 'tinyllama-1.1b')")


class TogglePrivacyRequest(BaseModel):
    enabled: bool = Field(..., description="Whether to force privacy mode (use fine-tuned model only)")


class ToggleAutoLearningRequest(BaseModel):
    enabled: bool = Field(..., description="Whether to enable automatic learning from chat interactions")


class MultiModalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    modality: Optional[str] = Field(
        default=None,
        description="Explicit modality: 'text', 'code', 'image', 'voice'. Auto-detected if omitted.",
    )
    attachments: Optional[List[Dict[str, Any]]] = Field(default=None)
    use_rag: bool = Field(default=True)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    save_training_example: bool = Field(
        default=True,
        description="Whether to save the response as a training example for the model.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    """Best-effort extraction of the caller's IP address."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def _audit(
    db: SupabaseClient,
    org_id: str,
    user_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Fire-and-forget audit log creation – never raises."""
    try:
        await db.create_audit_log(
            org_id=org_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
    except Exception as exc:
        logger.error(f"Audit log failed: {exc}")


async def generate_answer_with_context(
    query: str,
    context: List[Dict[str, Any]],
    temperature: float,
    system_prompt: Optional[str],
    org_niche: str,
    org_name: Optional[str] = None,
    user_name: Optional[str] = None,
    privacy_enabled: bool = True,
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> tuple:
    """
    Build messages from per-org system prompt + RAG context + user query,
    then call FreeAPIManager for an answer.

    Applies the PrivacyProxy to strip PII from the query before sending
    to any external API when privacy_enabled is True.

    Args:
        query: The raw user query text.
        context: RAG context chunks to include in the system prompt.
        temperature: Generation temperature (0.0–2.0).
        system_prompt: Per-org system prompt override; uses niche default if None.
        org_niche: Organisation's domain niche for default prompt selection.
        org_name: Organisation display name to redact from the query (optional).
        user_name: User display name to redact from the query (optional).
        privacy_enabled: When True (default), the PrivacyProxy sanitizes the
            query before it reaches any external API and rehydrates the response.

    Returns:
        Tuple of (response_text, api_used).
    """
    api_manager = get_api_manager()

    context_text = (
        "\n\n".join([c.get("content", "") for c in context]) if context else ""
    )

    system_msg = system_prompt or _build_default_system_prompt(org_niche)

    if context_text:
        system_msg += (
            "\n\nUse the following knowledge base context to provide accurate, well-sourced answers. "
            "Prioritize this context over general knowledge:\n" + context_text
        )

    # Privacy proxy: sanitize query before sending to external API
    sanitized_query = query
    replacements: Dict[str, str] = {}
    if privacy_enabled:
        try:
            from enterprise.privacy_proxy import get_privacy_proxy
            proxy = get_privacy_proxy()
            sanitized_query, replacements = proxy.sanitize_for_api(
                user_query=query,
                org_name=org_name,
                user_name=user_name,
            )
        except Exception as priv_exc:
            logger.warning(f"Privacy proxy failed (sending original): {priv_exc}")
            sanitized_query = query

    # Log privacy audit event (background, non-blocking)
    if replacements and org_id:
        try:
            from enterprise.privacy_proxy import get_privacy_proxy
            proxy = get_privacy_proxy()
            audit_event = proxy.build_audit_event(
                original_query=query,
                sanitized_query=sanitized_query,
                replacements=replacements,
                org_id=org_id,
                user_id=user_id,
            )
            db = get_supabase_client()
            await db.log_privacy_audit(audit_event)
        except Exception as audit_exc:
            logger.debug(f"Privacy audit logging skipped: {audit_exc}")

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": sanitized_query},
    ]

    response, api_used = await asyncio.to_thread(
        api_manager.chat,
        "openrouter", messages, temperature=temperature, enable_fallback=True,
    )

    # Rehydrate response with original entity references if any were replaced
    if replacements:
        try:
            from enterprise.privacy_proxy import get_privacy_proxy
            proxy = get_privacy_proxy()
            response = proxy.rehydrate_response(response, replacements)
        except Exception as rehy_exc:
            logger.warning(f"Response rehydration failed: {rehy_exc}")

    return response, api_used


async def _initialize_organization(
    org_id: str, model_id: str, niche: str, topics: List[str]
) -> None:
    """Background task: bootstrap a new organisation with training data + RAG + default assistants.
    
    AUTOMATED FLOW:
    1. Create default assistants for the niche
    2. Generate training data (100 examples)
    3. Initialize RAG knowledge base
    4. Calculate initial accuracy score
    5. Start continuous learning
    """
    logger.info(f"Initialising organisation {org_id} with niche: {niche}")
    try:
        # Create default assistants
        db = get_supabase_client(use_service_role=True)
        await db.create_default_assistants(org_id, niche)
        logger.info(f"Created default assistants for org {org_id}")

        # STEP 1: Generate initial training data
        pipeline = get_training_pipeline()
        if pipeline:
            logger.info(f"Auto-generating training data for niche: {niche}")
            await pipeline.generate_training_data(
                org_id=org_id,
                model_id=model_id,
                num_examples=100,
                topics=topics or None,
            )
            logger.info(f"Generated 100 training examples for org {org_id}")

        # STEP 2: Initialize RAG with niche knowledge
        rag = get_rag_system()
        if rag:
            await rag.initialize_org_knowledge(org_id=org_id, niche=niche)
            logger.info(f"RAG knowledge initialized for org {org_id}")

        # STEP 3: Calculate initial accuracy score
        try:
            from enterprise.accuracy_scorer import get_accuracy_scorer
            scorer = get_accuracy_scorer()
            if scorer:
                accuracy_result = await scorer.calculate_accuracy(
                    org_id=org_id,
                    model_id=model_id,
                    niche=niche,
                    use_cache=False
                )
                logger.info(f"Initial accuracy for org {org_id}: {accuracy_result.get('accuracy', 0)}%")
        except Exception as acc_exc:
            logger.warning(f"Could not calculate initial accuracy: {acc_exc}")

        logger.info(f"Organisation {org_id} initialised successfully - model is now training!")
    except Exception as exc:
        logger.error(f"Failed to initialise organisation {org_id}: {exc}")


async def _start_continuous_generation(org_id: str, model_id: str) -> None:
    """Background task: start continuous data generation for a new org."""
    try:
        from enterprise.data_generator import get_data_generator
        generator = get_data_generator()
        await generator.start_for_org(org_id, model_id)
        logger.info(f"Started continuous data generation for org {org_id}")
    except Exception as exc:
        logger.error(f"Failed to start data generation for org {org_id}: {exc}")


# ===================================================================
# PUBLIC ROUTES
# ===================================================================

@app.get("/health")
async def health_check():
    """System health check – handles None services safely. Does NOT initialize services."""
    db = await get_db()
    supabase_healthy = False
    try:
        supabase_healthy = await db.health_check()
    except Exception:
        pass

    # Check services without initializing them (avoids blocking on model downloads)
    rag_ready = _rag_system is not None and _rag_system.is_ready()
    fc_ready = _fact_checker is not None and _fact_checker.is_ready()

    overall = "healthy" if supabase_healthy else "degraded"

    return {
        "status": overall,
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "supabase": supabase_healthy,
            "rag_system": rag_ready,
            "fact_checker": fc_ready,
            "continuous_learner": get_continuous_learner() is not None,
            "training_pipeline": _training_pipeline is not None,
        },
    }


@app.get("/")
async def root():
    """API root – public landing."""
    return {
        "name": "PLM Enterprise API",
        "version": "2.0.0",
        "docs": "/docs",
    }


# ===================================================================
# AUTHENTICATED ROUTES
# ===================================================================

# ----- User profile ---------------------------------------------------

@app.get("/me")
async def get_current_user(
    auth: AuthContext = Depends(require_auth),
):
    """Return the authenticated user's profile (id, email, role, org_id)."""
    return {
        "user_id": auth.user_id,
        "email": auth.email,
        "role": auth.role,
        "org_id": auth.org_id,
        "auth_method": auth.auth_method,
    }


# ----- Organisations ---------------------------------------------------

@app.get("/organizations")
async def list_organizations(
    status: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """List organisations visible to the caller.

    JWT users see only their own org; service-role / API-key callers
    with no org_id constraint see all.
    """
    try:
        if auth.auth_method == "jwt":
            if auth.org_id:
                org = await db.get_organization(auth.org_id)
                orgs = [org] if org else []
            else:
                # JWT user with no org — return empty list, not all orgs
                orgs = []
        else:
            orgs = await db.list_organizations(status=status)
        return {"organizations": orgs, "count": len(orgs)}
    except Exception as exc:
        logger.error(f"list_organizations failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list organisations")


@app.get("/organizations/{org_id}")
async def get_organization(
    org_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get organisation details with statistics."""
    _verify_org_access(auth, org_id)
    try:
        org = await db.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        stats = await db.get_organization_stats(org_id)
        return {**org, "statistics": stats}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_organization failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch organisation")


# ----- Query -----------------------------------------------------------

@app.post("/organizations/{org_id}/models/{model_id}/query")
async def query_model(
    org_id: str,
    model_id: str,
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Main query endpoint.

    Flow:
    1. Fetch org & extract per-org system_prompt from org.metadata.
    2. Optionally retrieve RAG context via get_rag_system().
    3. Build messages: system prompt + context + user query.
    4. Call FreeAPIManager.chat().
    5. Optionally fact-check via get_fact_checker().
    6. Log query.
    7. Background: continuous learner processes the interaction.
    """
    _verify_org_access(auth, org_id)
    await check_query_limit(org_id, db)
    start_time = time.time()

    # -- Validate org & model -----------------------------------------------
    org = await db.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    model = await db.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if model.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Model not found in this organisation")

    # -- Per-org system prompt -----------------------------------------------
    org_metadata = org.get("metadata") or {}
    system_prompt = org_metadata.get("system_prompt")
    org_niche = org.get("niche", "general")

    try:
        # Step 1: RAG retrieval
        context: List[Dict[str, Any]] = []
        if request.use_rag:
            rag = get_rag_system()
            if rag and rag.is_ready():
                context = await rag.retrieve_context(
                    query=request.query, org_id=org_id, top_k=5
                )

        # Step 2: Try fine-tuned model FIRST, then fall back to API
        response_text = None
        api_used = None

        # 2a. Check if this model has real fine-tuned weights
        model_metrics = model.get("metrics") or {}
        has_adapter = model_metrics.get("has_adapter", False)
        adapter_path = model.get("model_path") or model_metrics.get("adapter_path")
        base_model_key = model.get("base_model", "tinyllama-1.1b")

        if has_adapter and adapter_path:
            server = get_model_server()
            if server and server.is_available():
                # Build messages with context
                context_text = (
                    "\n\n".join([c.get("content", "") for c in context]) if context else ""
                )
                sys_msg = system_prompt or _build_default_system_prompt(org_niche)
                if context_text:
                    sys_msg += (
                        "\n\nUse the following knowledge base context to provide accurate, well-sourced answers. "
                        "Prioritize this context over general knowledge:\n" + context_text
                    )

                messages = [
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": request.query},
                ]

                # Resolve HuggingFace model name from base_model key
                from enterprise.model_trainer import BASE_MODELS
                base_model_name = BASE_MODELS.get(base_model_key, base_model_key)

                result = await server.generate(
                    adapter_path=adapter_path,
                    base_model_name=base_model_name,
                    messages=messages,
                    temperature=request.temperature,
                )

                if result is not None:
                    response_text, gen_metadata = result
                    api_used = f"fine_tuned:{base_model_key}"
                    logger.info(
                        f"Query answered by fine-tuned model: {adapter_path} "
                        f"({gen_metadata.get('tokens_generated', '?')} tokens, "
                        f"{gen_metadata.get('generation_time_ms', '?')}ms)"
                    )

        # 2b. Fallback to API-based generation if no fine-tuned model or it failed
        if response_text is None:
            response_text, api_used = await generate_answer_with_context(
                query=request.query,
                context=context,
                temperature=request.temperature,
                system_prompt=system_prompt,
                org_niche=org_niche,
                org_id=org_id,
                user_id=auth.user_id,
            )

        # Step 3: Fact-check
        confidence = 0.8
        fact_check_results: List[Dict[str, Any]] = []
        if request.use_fact_check:
            fc = get_fact_checker()
            if fc and fc.is_ready():
                fact_check_results = await fc.verify_answer(
                    query=request.query,
                    answer=response_text,
                    context=context,
                )
                if fact_check_results:
                    confidence = sum(
                        r.get("confidence", 0) for r in fact_check_results
                    ) / len(fact_check_results)

        response_time_ms = int((time.time() - start_time) * 1000)

        # Step 4: Log query
        query_log = await db.log_query(
            org_id=org_id,
            model_id=model_id,
            query=request.query,
            response_text=response_text,
            confidence=confidence,
            response_time_ms=response_time_ms,
            user_id=auth.user_id,
        )

        # Step 5: Store fact-check results
        for fc_result in fact_check_results:
            try:
                await db.add_fact_check(
                    query_id=query_log["id"],
                    claim=fc_result.get("claim", ""),
                    verified=fc_result.get("verified", False),
                    confidence=fc_result.get("confidence", 0),
                    source=fc_result.get("source"),
                )
            except Exception as exc:
                logger.error(f"Failed to store fact-check result: {exc}")

        # Step 6: Background continuous learning
        learner = get_continuous_learner()
        if learner:
            background_tasks.add_task(
                learner.process_query,
                org_id=org_id,
                model_id=model_id,
                query=request.query,
                response=response_text,
                confidence=confidence,
            )

        # Audit
        background_tasks.add_task(
            _audit,
            db, org_id, auth.user_id, "query", "model",
            resource_id=model_id,
            details={"response_time_ms": response_time_ms},
            ip_address=_client_ip(req),
        )

        return {
            "query_id": query_log["id"],
            "response": response_text,
            "confidence": confidence,
            "response_time_ms": response_time_ms,
            "context_used": len(context) > 0,
            "fact_checked": request.use_fact_check and len(fact_check_results) > 0,
            "fact_check_results": fact_check_results if request.use_fact_check else [],
            "sources": [c.get("source") for c in context if c.get("source")] if context else [],
            "api_used": "plm",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Query failed: {exc}")
        raise HTTPException(status_code=500, detail="Query processing failed")


# ----- Feedback ---------------------------------------------------------

@app.post("/queries/{query_id}/feedback")
async def add_feedback(
    query_id: str,
    request: FeedbackRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Record user feedback on a query response."""
    try:
        # Verify the query exists and belongs to the caller's org
        query_row = (
            db.client.table("queries")
            .select("id, organization_id")
            .eq("id", query_id)
            .execute()
        )
        if not query_row.data:
            raise HTTPException(status_code=404, detail="Query not found")
        if not auth.org_id or query_row.data[0].get("organization_id") != auth.org_id:
            raise HTTPException(status_code=404, detail="Query not found")

        db.client.table("queries").update(
            {"feedback": request.feedback}
        ).eq("id", query_id).execute()

        learner = get_continuous_learner()
        if learner:
            background_tasks.add_task(
                learner.process_feedback,
                query_id=query_id,
                feedback=request.feedback,
                comment=request.comment,
            )

        return {
            "query_id": query_id,
            "feedback": request.feedback,
            "status": "recorded",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to record feedback: {exc}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")


# ----- Pet Status (PLM v2.0) -------------------------------------------

@app.get("/organizations/{org_id}/models/{model_id}/pet-status")
async def get_pet_status(
    org_id: str,
    model_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """
    Get the AI pet's current evolution status for an org/model.

    Returns stage (Egg → Legend), mood, XP, and personality prompt modifier
    computed from real training metrics.
    """
    _verify_org_access(auth, org_id)
    try:
        # Verify model exists and belongs to this org
        model = await db.get_model(model_id)
        if not model or model.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Model not found")

        from enterprise.pet_personality import get_pet_personality
        pet = get_pet_personality()
        status = await pet.get_pet_status(org_id=org_id, model_id=model_id)
        return status
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_pet_status failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch pet status")


# ----- Multi-Modal (PLM v2.0) ------------------------------------------

@app.post("/organizations/{org_id}/models/{model_id}/multi-modal")
async def multi_modal_query(
    org_id: str,
    model_id: str,
    request: MultiModalRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """
    Multi-modal query endpoint supporting text, code, image, and voice modalities.

    Auto-detects modality from the query if not explicitly specified.
    All modalities share the same RAG knowledge base and niche system prompt.
    """
    _verify_org_access(auth, org_id)
    await check_query_limit(org_id, db)
    start_time = time.time()

    org = await db.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    model = await db.get_model(model_id)
    if not model or model.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Model not found")

    org_metadata = org.get("metadata") or {}
    system_prompt = org_metadata.get("system_prompt")
    org_niche = org.get("niche", "general")

    try:
        # Fetch RAG context if requested
        context: List[Dict[str, Any]] = []
        if request.use_rag:
            rag = get_rag_system()
            if rag and rag.is_ready():
                context = await rag.retrieve_context(
                    query=request.query, org_id=org_id, top_k=5
                )

        # Route to appropriate modality handler
        from enterprise.modality_router import get_modality_router
        router = get_modality_router()

        result = await router.route_query(
            query=request.query,
            org_id=org_id,
            model_id=model_id,
            modality=request.modality,
            attachments=request.attachments,
            system_prompt=system_prompt,
            org_niche=org_niche,
            temperature=request.temperature,
            context=context,
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        # Log query to DB
        query_log = await db.log_query(
            org_id=org_id,
            model_id=model_id,
            query=request.query,
            response_text=result["response"],
            confidence=0.8,
            response_time_ms=response_time_ms,
            user_id=auth.user_id,
        )

        # Optionally save as training example
        if request.save_training_example and result.get("training_example"):
            try:
                ex = result["training_example"]
                db.client.table("training_data").insert({
                    "organization_id": org_id,
                    "model_id": model_id,
                    "instruction": ex.get("instruction", request.query),
                    "output": ex.get("output", result["response"]),
                    "input_text": ex.get("input_text", ""),
                    "metadata": ex.get("metadata", {}),
                    "quality_score": ex.get("quality_score", 0.8),
                    "validated": False,
                }).execute()
            except Exception as save_exc:
                logger.warning(f"Failed to save training example: {save_exc}")

        # Log to multi_modal_queries table (graceful — table may not exist yet)
        try:
            db.client.table("multi_modal_queries").insert({
                "organization_id": org_id,
                "model_id": model_id,
                "query_id": query_log["id"],
                "modality": result["modality"],
                "query": request.query,
                "response": result["response"],
                "response_time_ms": response_time_ms,
            }).execute()
        except Exception:
            pass  # Table may not exist in older deployments

        # Audit
        background_tasks.add_task(
            _audit,
            db, org_id, auth.user_id, "multi_modal_query", "model",
            resource_id=model_id,
            details={"modality": result["modality"], "response_time_ms": response_time_ms},
            ip_address=_client_ip(req),
        )

        return {
            "query_id": query_log["id"],
            "response": result["response"],
            "modality": result["modality"],
            "detected_language": result.get("detected_language"),
            "degraded_from": result.get("degraded_from"),
            "response_time_ms": response_time_ms,
            "context_used": len(context) > 0,
            "api_used": result.get("api_used", "plm"),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Multi-modal query failed: {exc}")
        raise HTTPException(status_code=500, detail="Multi-modal query processing failed")


# ----- Models (list / detail) ------------------------------------------

@app.get("/organizations/{org_id}/models")
async def list_models(
    org_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """List all models for an organisation."""
    _verify_org_access(auth, org_id)
    try:
        models = await db.list_models(org_id)
        return {"models": models, "count": len(models)}
    except Exception as exc:
        logger.error(f"list_models failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list models")


@app.get("/models/{model_id}")
async def get_model(
    model_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get model details with performance metrics."""
    try:
        model = await db.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        # Verify the model belongs to the caller's org (IDOR protection)
        if auth.org_id and model.get("organization_id") != auth.org_id:
            raise HTTPException(status_code=404, detail="Model not found")
        if not auth.org_id:
            raise HTTPException(status_code=403, detail="No organization context")
        metrics = await db.get_model_metrics(model_id)
        return {**model, "performance_metrics": metrics}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_model failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch model")


# ----- Analytics --------------------------------------------------------

@app.get("/organizations/{org_id}/analytics")
async def get_analytics(
    org_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Comprehensive organisation analytics."""
    _verify_org_access(auth, org_id)
    try:
        stats = await db.get_organization_stats(org_id)
        recent_queries = await db.get_queries(org_id, limit=10)
        return {"statistics": stats, "recent_queries": recent_queries}
    except Exception as exc:
        logger.error(f"get_analytics failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")


# ----- Knowledge base (read) -------------------------------------------

@app.get("/organizations/{org_id}/knowledge")
async def list_knowledge(
    org_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
    category: Optional[str] = None,
):
    """List knowledge-base entries for an organisation. Optionally filter by ?category=X."""
    _verify_org_access(auth, org_id)
    try:
        query = (
            db.client.table("knowledge_base")
            .select("id, content, source, category, source_type, file_name, chunk_index, metadata, created_at")
            .eq("organization_id", org_id)
        )
        if category:
            query = query.eq("category", category)
        response = query.order("created_at", desc=True).limit(200).execute()
        entries = response.data or []
        return {"knowledge": entries, "count": len(entries)}
    except Exception as exc:
        logger.error(f"list_knowledge failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list knowledge entries")


# ----- Query history ----------------------------------------------------

@app.get("/organizations/{org_id}/queries")
async def list_queries(
    org_id: str,
    limit: int = 100,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Query history for an organisation."""
    _verify_org_access(auth, org_id)
    try:
        queries = await db.get_queries(org_id, limit=limit)
        return {"queries": queries, "count": len(queries)}
    except Exception as exc:
        logger.error(f"list_queries failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch query history")


# ----- Learning stats ---------------------------------------------------

@app.get("/organizations/{org_id}/learning-stats/{model_id}")
async def learning_stats(
    org_id: str,
    model_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Continuous-learning statistics for a model."""
    _verify_org_access(auth, org_id)
    try:
        learner = get_continuous_learner()
        if not learner:
            raise HTTPException(
                status_code=503,
                detail="Continuous learner service is unavailable",
            )
        stats = await learner.get_learning_stats(org_id, model_id)
        return stats
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"learning_stats failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch learning stats")


# ===================================================================
# ADMIN ROUTES  (require admin or owner role)
# ===================================================================

# ----- Create organisation ----------------------------------------------

@app.post("/organizations", status_code=201)
async def create_organization(
    request: CreateOrganizationRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Create a new organisation and bootstrap its first model.

    Any authenticated user can create an org (to solve the chicken-and-egg
    problem for new signups). The creator becomes the org owner.
    """
    try:
        org = await db.create_organization(
            name=request.name,
            slug=request.slug,
            niche=request.niche,
            tier=request.tier,
            system_prompt=request.system_prompt,
        )

        model = await db.create_model(
            org_id=org["id"],
            name=f"{request.name} Model v1",
        )

        # Link the creator as the org owner — this MUST succeed
        if auth.user_id:
            try:
                await db.create_user(
                    user_id=auth.user_id,
                    org_id=org["id"],
                    email=auth.email or "",
                    role="owner",
                )
            except Exception as user_exc:
                logger.error(f"CRITICAL: Failed to link creator as owner: {user_exc}")
                # Clean up: delete the orphaned org and model to avoid ghost data
                try:
                    db.client.table("models").delete().eq("id", model["id"]).execute()
                    db.client.table("organizations").delete().eq("id", org["id"]).execute()
                except Exception:
                    pass
                raise HTTPException(
                    status_code=500,
                    detail="Failed to link your account to the new organisation. Please try again.",
                )

        # Mark onboarding as completed now that org + model + owner are set up
        try:
            await db.update_organization(org["id"], {"onboarding_completed": True})
        except Exception as onb_exc:
            logger.warning(f"Failed to set onboarding_completed: {onb_exc}")

        background_tasks.add_task(
            _initialize_organization,
            org_id=org["id"],
            model_id=model["id"],
            niche=request.niche,
            topics=request.topics,
        )

        # Start continuous data generation for this org's model
        background_tasks.add_task(
            _start_continuous_generation,
            org_id=org["id"],
            model_id=model["id"],
        )

        background_tasks.add_task(
            _audit,
            db, org["id"], auth.user_id, "create", "organization",
            resource_id=org["id"],
            details={"name": request.name, "slug": request.slug},
            ip_address=_client_ip(req),
        )

        logger.info(f"Created organisation: {request.name} (ID: {org['id']})")

        return {
            "organization_id": org["id"],
            "model_id": model["id"],
            "status": "created",
            "message": "Organisation created. Initialising in background.",
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as exc:
        logger.error(f"create_organization failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create organisation")


# ----- Update organisation ----------------------------------------------

@app.patch("/organizations/{org_id}")
async def update_organization(
    org_id: str,
    request: UpdateOrgRequest,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Update organisation details (name, niche, system_prompt)."""
    _verify_org_access(auth, org_id)
    try:
        org = await db.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        updates: Dict[str, Any] = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.niche is not None:
            updates["niche"] = request.niche
        if request.system_prompt is not None:
            metadata = org.get("metadata") or {}
            metadata["system_prompt"] = request.system_prompt
            updates["metadata"] = metadata

        if not updates:
            return org

        updated_org = await db.update_organization(org_id, updates)

        await _audit(
            db, org_id, auth.user_id, "update", "organization",
            resource_id=org_id,
            details={"fields": list(updates.keys())},
            ip_address=_client_ip(req),
        )

        return updated_org
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"update_organization failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update organisation")


# ----- Create model -----------------------------------------------------

@app.post("/organizations/{org_id}/models", status_code=201)
async def create_model(
    org_id: str,
    request: CreateModelRequest,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Create a new model for an organisation."""
    _verify_org_access(auth, org_id)
    try:
        org = await db.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        model = await db.create_model(
            org_id=org_id,
            name=request.name,
            base_model=request.base_model,
        )

        await _audit(
            db, org_id, auth.user_id, "create", "model",
            resource_id=model["id"],
            details={"name": request.name, "base_model": request.base_model},
            ip_address=_client_ip(req),
        )

        return model
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_model failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create model")


# ----- Generate training data -------------------------------------------

@app.post("/organizations/{org_id}/models/{model_id}/generate-data")
async def generate_training_data(
    org_id: str,
    model_id: str,
    request: GenerateDataRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Kick off background training-data generation."""
    _verify_org_access(auth, org_id)
    model = await db.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Model not found in this organisation")

    pipeline = get_training_pipeline()
    if not pipeline:
        raise HTTPException(status_code=503, detail="Training pipeline service is unavailable")

    background_tasks.add_task(
        pipeline.generate_training_data,
        org_id=org_id,
        model_id=model_id,
        num_examples=request.num_examples,
        topics=request.topics,
    )

    background_tasks.add_task(
        _audit,
        db, org_id, auth.user_id, "generate_data", "model",
        resource_id=model_id,
        details={"num_examples": request.num_examples},
        ip_address=_client_ip(req),
    )

    return {
        "status": "started",
        "num_examples": request.num_examples,
        "message": "Training data generation started in background",
    }


# ----- Start training ---------------------------------------------------

@app.post("/organizations/{org_id}/models/{model_id}/train")
async def start_training(
    org_id: str,
    model_id: str,
    request: StartTrainingRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Start a model training job."""
    _verify_org_access(auth, org_id)
    model = await db.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Model not found in this organisation")

    pipeline = get_training_pipeline()
    if not pipeline:
        raise HTTPException(status_code=503, detail="Training pipeline service is unavailable")

    # Verify training data exists before creating a job
    try:
        td_response = (
            db.client.table("training_data")
            .select("id", count="exact")
            .eq("organization_id", org_id)
            .eq("model_id", model_id)
            .execute()
        )
        td_count = td_response.count if td_response.count is not None else len(td_response.data or [])
        if td_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No training data available. Generate training data first before starting training.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # If count check fails, let training pipeline handle it

    try:
        # Build training config with backend and base_model preferences
        training_config = request.training_config.copy()
        if request.backend:
            training_config["backend"] = request.backend
        if request.base_model:
            training_config["base_model"] = request.base_model

        job = await db.create_training_job(
            org_id=org_id,
            model_id=model_id,
            training_config=training_config,
        )

        background_tasks.add_task(
            pipeline.train_model,
            job_id=job["id"],
            org_id=org_id,
            model_id=model_id,
            config=training_config,
        )

        background_tasks.add_task(
            _audit,
            db, org_id, auth.user_id, "start_training", "model",
            resource_id=model_id,
            details={"job_id": job["id"]},
            ip_address=_client_ip(req),
        )

        # Include training time estimates for the selected backend
        estimate = None
        selected_backend = training_config.get("backend", "auto")
        base_model_key = training_config.get("base_model", model.get("base_model", "tinyllama-1.1b"))
        if selected_backend in ("kaggle", "auto", None):
            try:
                from enterprise.model_trainer import KaggleNotebookTrainer
                estimate = KaggleNotebookTrainer.estimate_training_time(base_model_key, td_count if td_count else 100)
            except Exception:
                pass

        return {
            "id": job["id"],
            "job_id": job["id"],
            "status": "queued",
            "progress": 0,
            "message": "Model training started in background",
            "backend": selected_backend,
            "training_estimate": estimate,
        }
    except Exception as exc:
        logger.error(f"start_training failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to start training")


# ----- Training job status ----------------------------------------------

@app.get("/training-backends")
async def get_training_backends(
    auth: AuthContext = Depends(require_auth),
):
    """List available training backends and supported base models."""
    available = []
    base_models = {}
    kaggle_estimates = {}
    try:
        from enterprise.model_trainer import get_model_trainer, BASE_MODELS, KaggleNotebookTrainer
        trainer = get_model_trainer()
        available = trainer.get_available_backends()
        base_models = {
            key: {"hf_name": val, "recommended_vram": _model_vram(key)}
            for key, val in BASE_MODELS.items()
        }
        # Add Kaggle training time estimates
        if "kaggle" in available:
            for key in BASE_MODELS:
                kaggle_estimates[key] = KaggleNotebookTrainer.estimate_training_time(key, 500)
    except Exception:
        pass

    return {
        "available_backends": available,
        "base_models": base_models,
        "has_gpu": _has_gpu(),
        "kaggle_estimates": kaggle_estimates,
    }


def _model_vram(key: str) -> str:
    """Approximate VRAM needed for QLoRA fine-tuning."""
    sizes = {
        "tinyllama-1.1b": "6GB", "llama-3.2-1b": "8GB", "llama-3.2-3b": "12GB",
        "phi-3-mini": "14GB", "mistral-7b": "20GB", "llama-3.1-8b": "24GB",
    }
    return sizes.get(key, "unknown")


def _has_gpu() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


@app.get("/training-jobs/{job_id}")
async def get_training_job(
    job_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get training job status."""
    try:
        response = (
            db.client.table("training_jobs")
            .select("*")
            .eq("id", job_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Training job not found")
        job = response.data[0]
        # Verify the job belongs to the caller's org (IDOR protection)
        if not auth.org_id or job.get("organization_id") != auth.org_id:
            raise HTTPException(status_code=404, detail="Training job not found")
        return job
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_training_job failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch training job")


# ----- Knowledge base (admin write / delete) ----------------------------

@app.post("/organizations/{org_id}/knowledge", status_code=201)
async def add_knowledge(
    org_id: str,
    request: AddKnowledgeRequest,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Add knowledge-base entry (with embedding via RAG system)."""
    _verify_org_access(auth, org_id)
    try:
        rag = get_rag_system()
        if rag and rag.is_ready():
            success = await rag.add_knowledge(
                org_id=org_id,
                content=request.content,
                source=request.source,
            )
            if not success:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to add knowledge via RAG system",
                )
        else:
            # RAG system not available -- cannot generate real embeddings
            raise HTTPException(
                status_code=503,
                detail="RAG system is not ready. Knowledge cannot be added without embeddings.",
            )

        await _audit(
            db, org_id, auth.user_id, "add", "knowledge",
            details={"source": request.source, "content_length": len(request.content)},
            ip_address=_client_ip(req),
        )

        return {"status": "added", "org_id": org_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"add_knowledge failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to add knowledge entry")


@app.delete("/organizations/{org_id}/knowledge/{kb_id}")
async def delete_knowledge(
    org_id: str,
    kb_id: str,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Delete a knowledge-base entry."""
    _verify_org_access(auth, org_id)
    try:
        deleted = await db.delete_knowledge(kb_id, org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Knowledge entry not found")

        await _audit(
            db, org_id, auth.user_id, "delete", "knowledge",
            resource_id=kb_id,
            ip_address=_client_ip(req),
        )

        return {"status": "deleted", "id": kb_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_knowledge failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete knowledge entry")


@app.post("/organizations/{org_id}/knowledge/upload", status_code=201)
async def upload_knowledge_file(
    org_id: str,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
    category: str = "general",
):
    """Upload a file (PDF, TXT, CSV) to the knowledge base.

    The file is processed, chunked, embedded, and stored in the knowledge base.
    Max file size: 10MB.
    """
    from fastapi import UploadFile, File
    _verify_org_access(auth, org_id)

    # Parse multipart form
    form = await req.form()
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise HTTPException(status_code=400, detail="No file provided. Send as multipart/form-data with field name 'file'.")

    category_val = form.get("category", category)
    if isinstance(category_val, str):
        category = category_val

    file_bytes = await file.read()
    raw_filename = getattr(file, "filename", "upload.txt") or "upload.txt"
    # Sanitize filename: strip path separators, null bytes, control chars
    import re
    file_name = re.sub(r'[/\\:\x00-\x1f]', '_', raw_filename.split('/')[-1].split('\\')[-1])
    if not file_name or file_name.startswith('.'):
        file_name = "upload.txt"

    # Size check (10MB)
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    if not file_bytes:
        raise HTTPException(status_code=400, detail="File is empty.")

    try:
        from enterprise.document_processor import DocumentProcessor
        processor = DocumentProcessor()
        content_type = getattr(file, "content_type", None)
        chunks = processor.process_file(file_bytes, file_name, content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.error(f"Document processing failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to process document")

    # Store each chunk in the knowledge base
    rag = get_rag_system()
    if not rag or not rag.is_ready():
        # Wait briefly — RAG may be loading on first request after startup
        import asyncio as _aio
        for _attempt in range(3):
            await _aio.sleep(2)
            rag = get_rag_system()
            if rag and rag.is_ready():
                break
        if not rag or not rag.is_ready():
            raise HTTPException(
                status_code=503,
                detail="Knowledge base embedding system is not ready. Please try again in a few seconds.",
            )

    added = 0
    failed = 0
    for chunk_data in chunks:
        try:
            success = await rag.add_knowledge(
                content=chunk_data["content"],
                org_id=org_id,
                source=chunk_data.get("source", file_name),
                metadata={
                    "category": category,
                    "source_type": chunk_data.get("source_type", "text"),
                    "file_name": chunk_data.get("file_name", file_name),
                    "chunk_index": chunk_data.get("chunk_index", 0),
                },
            )
            if success:
                added += 1
            else:
                failed += 1
                logger.warning(f"Embedding failed for chunk {chunk_data.get('chunk_index', '?')} of {file_name}")
        except Exception as exc:
            failed += 1
            logger.warning(f"Failed to store chunk {chunk_data.get('chunk_index', '?')}: {exc}")

    if added == 0:
        raise HTTPException(status_code=500, detail="Failed to store any document chunks")

    await _audit(
        db, org_id, auth.user_id, "upload", "knowledge",
        details={"file_name": file_name, "chunks_added": added, "category": category},
        ip_address=_client_ip(req),
    )

    return {
        "status": "uploaded",
        "file_name": file_name,
        "chunks_added": added,
        "chunks_failed": failed,
        "total_chunks": len(chunks),
        "category": category,
    }


@app.get("/organizations/{org_id}/knowledge/categories")
async def list_knowledge_categories(
    org_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """List distinct knowledge base categories for an organization."""
    _verify_org_access(auth, org_id)
    try:
        response = (
            db.client.table("knowledge_base")
            .select("category")
            .eq("organization_id", org_id)
            .execute()
        )
        cats = list({row.get("category", "general") for row in response.data if row.get("category")})
        cats.sort()
        return {"categories": cats}
    except Exception as exc:
        logger.error(f"list_knowledge_categories failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list categories")


# ----- API key management (admin) ---------------------------------------

@app.post("/organizations/{org_id}/api-keys", status_code=201)
async def create_api_key_endpoint(
    org_id: str,
    request: CreateApiKeyRequest,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Create a new API key for the organisation."""
    _verify_org_access(auth, org_id)
    try:
        key_data = await create_api_key(org_id=org_id, name=request.name, db=db)

        await _audit(
            db, org_id, auth.user_id, "create", "api_key",
            resource_id=key_data["id"],
            details={"name": request.name},
            ip_address=_client_ip(req),
        )

        return key_data
    except Exception as exc:
        logger.error(f"create_api_key failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create API key")


@app.get("/organizations/{org_id}/api-keys")
async def list_api_keys(
    org_id: str,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """List API keys for the organisation (hash never exposed)."""
    _verify_org_access(auth, org_id)
    try:
        keys = await db.list_api_keys(org_id)
        return {"api_keys": keys, "count": len(keys)}
    except Exception as exc:
        logger.error(f"list_api_keys failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list API keys")


@app.delete("/organizations/{org_id}/api-keys/{key_id}")
async def revoke_api_key_endpoint(
    org_id: str,
    key_id: str,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Revoke an API key."""
    _verify_org_access(auth, org_id)
    try:
        revoked = await revoke_api_key(key_id=key_id, org_id=org_id, db=db)
        if not revoked:
            raise HTTPException(status_code=404, detail="API key not found")

        await _audit(
            db, org_id, auth.user_id, "revoke", "api_key",
            resource_id=key_id,
            ip_address=_client_ip(req),
        )

        return {"status": "revoked", "id": key_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"revoke_api_key failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to revoke API key")


# ===================================================================
# OWNER ROUTES  (require owner role)
# ===================================================================

# ----- User management --------------------------------------------------

@app.get("/organizations/{org_id}/users")
async def list_users(
    org_id: str,
    auth: AuthContext = Depends(require_owner),
    db: SupabaseClient = Depends(get_db),
):
    """List all users in the organisation."""
    _verify_org_access(auth, org_id)
    try:
        users = await db.list_org_users(org_id)
        return {"users": users, "count": len(users)}
    except Exception as exc:
        logger.error(f"list_users failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list users")


@app.patch("/organizations/{org_id}/users/{user_id}/role")
async def update_user_role(
    org_id: str,
    user_id: str,
    request: UpdateUserRoleRequest,
    req: Request,
    auth: AuthContext = Depends(require_owner),
    db: SupabaseClient = Depends(get_db),
):
    """Update a user's role within the organisation."""
    _verify_org_access(auth, org_id)
    try:
        # Verify user belongs to org
        user = await db.get_user(user_id)
        if not user or user.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="User not found in this organisation")

        # Prevent owners from demoting themselves
        if user_id == auth.user_id and request.role != "owner":
            raise HTTPException(
                status_code=400,
                detail="Cannot change your own role. Ask another owner.",
            )

        updated = await db.update_user_role(user_id, request.role)

        await _audit(
            db, org_id, auth.user_id, "update_role", "user",
            resource_id=user_id,
            details={"new_role": request.role, "old_role": user.get("role")},
            ip_address=_client_ip(req),
        )

        return updated
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"update_user_role failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update user role")


# ----- Audit logs -------------------------------------------------------

@app.get("/organizations/{org_id}/audit-logs")
async def get_audit_logs(
    org_id: str,
    limit: int = 100,
    auth: AuthContext = Depends(require_owner),
    db: SupabaseClient = Depends(get_db),
):
    """Retrieve audit logs for the organisation."""
    _verify_org_access(auth, org_id)
    try:
        logs = await db.get_audit_logs(org_id, limit=limit)
        return {"audit_logs": logs, "count": len(logs)}
    except Exception as exc:
        logger.error(f"get_audit_logs failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch audit logs")


# ===================================================================
# BILLING ROUTES
# ===================================================================

@app.post("/billing/checkout")
async def create_checkout(
    tier: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Create a Stripe checkout session for upgrading org tier."""
    if not auth.org_id:
        raise HTTPException(status_code=400, detail="No organization linked to this account")

    try:
        from enterprise.billing import get_billing_manager

        billing = get_billing_manager()
        if not billing.is_configured:
            raise HTTPException(status_code=503, detail="Billing is not configured")

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        result = await billing.create_checkout_session(
            org_id=auth.org_id,
            tier=tier,
            success_url=f"{frontend_url}/dashboard?billing=success",
            cancel_url=f"{frontend_url}/dashboard?billing=cancelled",
        )

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_checkout failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@app.post("/billing/webhook")
async def stripe_webhook(request: Request, db: SupabaseClient = Depends(get_db)):
    """Handle Stripe webhook events. No auth required -- verified by Stripe signature."""
    try:
        from enterprise.billing import get_billing_manager

        billing = get_billing_manager()
        if not billing.is_configured:
            return {"status": "billing not configured"}

        payload = await request.body()
        sig_header = request.headers.get("stripe-signature", "")

        result = await billing.handle_webhook(payload, sig_header)

        if result.get("action") == "activate_tier":
            org_id = result["org_id"]
            tier = result["tier"]
            await db.update_organization(org_id, {"tier": tier})
            logger.info(f"Activated tier {tier} for org {org_id}")

        elif result.get("action") == "payment_failed":
            logger.warning(f"Payment failed: {result}")

        return {"status": "processed", "action": result.get("action")}

    except Exception as exc:
        logger.error(f"Stripe webhook failed: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/billing/usage")
async def get_billing_usage(
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get current billing usage for the authenticated org."""
    if not auth.org_id:
        raise HTTPException(status_code=400, detail="No organization linked")

    try:
        from enterprise.billing import get_billing_manager

        billing = get_billing_manager()
        org = await db.get_organization(auth.org_id)
        tier = org.get("tier", "starter") if org else "starter"

        # Count queries this month
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0).isoformat()
        response = (
            db.client.table("queries")
            .select("id", count="exact")
            .eq("organization_id", auth.org_id)
            .gte("created_at", month_start)
            .execute()
        )
        current_queries = response.count if response.count is not None else len(response.data or [])

        usage = await billing.check_usage(auth.org_id, tier, current_queries)
        usage["tier"] = tier
        usage["limits"] = billing.get_tier_limits(tier)
        return usage
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_billing_usage failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch usage")


# ===================================================================
# INVITATIONS
# ===================================================================

@app.post("/organizations/{org_id}/invitations", status_code=201)
async def create_invitation(
    org_id: str,
    request: CreateInvitationRequest,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Send an invitation to join the organization."""
    _verify_org_access(auth, org_id)
    try:
        # Check if user is already a member
        existing = await db.get_user_by_email(request.email)
        if existing and existing.get("organization_id") == org_id:
            raise HTTPException(status_code=409, detail="User is already a member of this organization")

        invitation = await db.create_invitation(
            org_id=org_id,
            email=request.email,
            role=request.role,
            invited_by=auth.user_id,
        )

        await _audit(
            db, org_id, auth.user_id, "create", "invitation",
            resource_id=invitation["id"],
            details={"email": request.email, "role": request.role},
            ip_address=_client_ip(req),
        )

        return invitation
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_invitation failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create invitation")


@app.get("/organizations/{org_id}/invitations")
async def list_invitations(
    org_id: str,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """List invitations for the organization."""
    _verify_org_access(auth, org_id)
    try:
        invites = await db.list_invitations(org_id)
        return {"invitations": invites, "count": len(invites)}
    except Exception as exc:
        logger.error(f"list_invitations failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list invitations")


@app.delete("/organizations/{org_id}/invitations/{invitation_id}")
async def revoke_invitation(
    org_id: str,
    invitation_id: str,
    req: Request,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Revoke a pending invitation."""
    _verify_org_access(auth, org_id)
    try:
        revoked = await db.revoke_invitation(invitation_id, org_id)
        if not revoked:
            raise HTTPException(status_code=404, detail="Invitation not found or already used")
        return {"status": "revoked", "id": invitation_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"revoke_invitation failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to revoke invitation")


@app.get("/invitations/{token}")
async def get_invitation_details(
    token: str,
    db: SupabaseClient = Depends(get_db),
):
    """Get invitation details by token (public endpoint for accept page)."""
    try:
        invitation = await db.get_invitation_by_token(token)
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found or expired")
        # Check expiry
        from datetime import datetime as dt
        expires_at = dt.fromisoformat(invitation["expires_at"].replace("Z", "+00:00"))
        if expires_at.replace(tzinfo=None) < dt.utcnow():
            raise HTTPException(status_code=410, detail="Invitation has expired")
        return {
            "id": invitation["id"],
            "email": invitation["email"],
            "role": invitation["role"],
            "organization_name": invitation.get("organizations", {}).get("name", "Unknown"),
            "expires_at": invitation["expires_at"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_invitation_details failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch invitation")


@app.post("/invitations/accept")
async def accept_invitation(
    request: AcceptInvitationRequest,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Accept an invitation and join the organization."""
    try:
        invitation = await db.get_invitation_by_token(request.token)
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found or already used")

        # Check expiry
        from datetime import datetime as dt
        expires_at = dt.fromisoformat(invitation["expires_at"].replace("Z", "+00:00"))
        if expires_at.replace(tzinfo=None) < dt.utcnow():
            raise HTTPException(status_code=410, detail="Invitation has expired")

        # Check email matches
        if auth.email and invitation["email"].lower() != auth.email.lower():
            raise HTTPException(
                status_code=403,
                detail=f"Invitation was sent to {invitation['email']}, but you are logged in as {auth.email}"
            )

        org_id = invitation["organization_id"]

        # Check if user already in this org
        existing = await db.get_user(auth.user_id)
        if existing and existing.get("organization_id") == org_id:
            # Already a member, just mark invite accepted
            await db.accept_invitation(invitation["id"])
            return {"status": "already_member", "organization_id": org_id}

        # Create user record in org
        if existing:
            # User exists but in different org - update their org
            await db.client.table("users").update({
                "organization_id": org_id,
                "role": invitation["role"],
            }).eq("id", auth.user_id).execute()
        else:
            # New user record
            await db.create_user(
                user_id=auth.user_id,
                org_id=org_id,
                email=auth.email or invitation["email"],
                role=invitation["role"],
            )

        # Mark invitation accepted
        await db.accept_invitation(invitation["id"])

        return {"status": "accepted", "organization_id": org_id, "role": invitation["role"]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"accept_invitation failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to accept invitation")


# ===================================================================
# ASSISTANTS
# ===================================================================

@app.get("/organizations/{org_id}/assistants")
async def list_assistants(
    org_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """List assistants for the organization."""
    _verify_org_access(auth, org_id)
    try:
        assistants = await db.list_assistants(org_id)
        return {"assistants": assistants, "count": len(assistants)}
    except Exception as exc:
        logger.error(f"list_assistants failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list assistants")


@app.get("/organizations/{org_id}/assistants/{assistant_id}")
async def get_assistant_detail(
    org_id: str,
    assistant_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get assistant details."""
    _verify_org_access(auth, org_id)
    try:
        assistant = await db.get_assistant(assistant_id)
        if not assistant or assistant.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Assistant not found")
        return assistant
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_assistant failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch assistant")


@app.post("/organizations/{org_id}/assistants", status_code=201)
async def create_assistant_endpoint(
    org_id: str,
    request: CreateAssistantRequest,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Create a new assistant for the organization."""
    _verify_org_access(auth, org_id)
    try:
        assistant = await db.create_assistant(
            org_id=org_id,
            name=request.name,
            system_prompt=request.system_prompt,
            assistant_type=request.assistant_type,
            description=request.description,
            icon=request.icon,
            temperature=request.temperature,
            use_rag=request.use_rag,
            knowledge_categories=request.knowledge_categories,
        )
        return assistant
    except Exception as exc:
        logger.error(f"create_assistant failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create assistant")


@app.patch("/organizations/{org_id}/assistants/{assistant_id}")
async def update_assistant_endpoint(
    org_id: str,
    assistant_id: str,
    request: UpdateAssistantRequest,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Update an assistant."""
    _verify_org_access(auth, org_id)
    try:
        existing = await db.get_assistant(assistant_id)
        if not existing or existing.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Assistant not found")
        updates: Dict[str, Any] = {}
        for field in ("name", "system_prompt", "description", "icon", "temperature", "use_rag", "knowledge_categories"):
            val = getattr(request, field, None)
            if val is not None:
                updates[field] = val
        if not updates:
            return existing
        updated = await db.update_assistant(assistant_id, updates)
        return updated
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"update_assistant failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update assistant")


@app.delete("/organizations/{org_id}/assistants/{assistant_id}")
async def delete_assistant_endpoint(
    org_id: str,
    assistant_id: str,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Delete an assistant."""
    _verify_org_access(auth, org_id)
    try:
        deleted = await db.delete_assistant(assistant_id, org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Assistant not found")
        return {"status": "deleted", "id": assistant_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_assistant failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete assistant")


# ===================================================================
# ONBOARDING STATUS
# ===================================================================

@app.get("/me/onboarding-status")
async def get_onboarding_status(
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Check if user has completed onboarding (has org with onboarding_completed=true)."""
    if not auth.org_id:
        return {
            "onboarding_completed": False,
            "has_organization": False,
            "org_id": None,
        }
    org = await db.get_organization(auth.org_id)
    if not org:
        return {
            "onboarding_completed": False,
            "has_organization": False,
            "org_id": None,
        }
    return {
        "onboarding_completed": org.get("onboarding_completed", False),
        "has_organization": True,
        "org_id": auth.org_id,
        "org_name": org.get("name"),
    }


# ===================================================================
# CONVERSATIONS
# ===================================================================

@app.post("/organizations/{org_id}/conversations", status_code=201)
async def create_conversation(
    org_id: str,
    request: CreateConversationRequest,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Create a new conversation."""
    _verify_org_access(auth, org_id)
    try:
        conv = await db.create_conversation(
            org_id=org_id,
            user_id=auth.user_id,
            model_id=request.model_id,
            title=request.title or "New Conversation",
            assistant_id=request.assistant_id,
        )
        return conv
    except Exception as exc:
        logger.error(f"create_conversation failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")


@app.get("/organizations/{org_id}/conversations")
async def list_conversations(
    org_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """List conversations for the authenticated user in the org."""
    _verify_org_access(auth, org_id)
    try:
        convs = await db.list_conversations(org_id, user_id=auth.user_id)
        return {"conversations": convs, "count": len(convs)}
    except Exception as exc:
        logger.error(f"list_conversations failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@app.get("/organizations/{org_id}/conversations/{conversation_id}")
async def get_conversation(
    org_id: str,
    conversation_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get a conversation with its messages."""
    _verify_org_access(auth, org_id)
    try:
        conv = await db.get_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conv.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # IDOR: only allow user's own conversations
        if auth.user_id and conv.get("user_id") and conv["user_id"] != auth.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = await db.get_messages(conversation_id)
        return {**conv, "messages": messages}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_conversation failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch conversation")


@app.patch("/organizations/{org_id}/conversations/{conversation_id}")
async def update_conversation_endpoint(
    org_id: str,
    conversation_id: str,
    request: UpdateConversationRequest,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Update conversation title."""
    _verify_org_access(auth, org_id)
    try:
        conv = await db.get_conversation(conversation_id)
        if not conv or conv.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if auth.user_id and conv.get("user_id") and conv["user_id"] != auth.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        updates: Dict[str, Any] = {}
        if request.title is not None:
            updates["title"] = request.title
        if not updates:
            return conv
        updated = await db.update_conversation(conversation_id, updates)
        return updated
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"update_conversation failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update conversation")


@app.delete("/organizations/{org_id}/conversations/{conversation_id}")
async def delete_conversation(
    org_id: str,
    conversation_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Archive a conversation."""
    _verify_org_access(auth, org_id)
    try:
        conv = await db.get_conversation(conversation_id)
        if not conv or conv.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if auth.user_id and conv.get("user_id") and conv["user_id"] != auth.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        archived = await db.archive_conversation(conversation_id)
        if not archived:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"status": "archived", "id": conversation_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_conversation failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to archive conversation")


@app.get("/organizations/{org_id}/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    org_id: str,
    conversation_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get all messages in a conversation (chat history)."""
    _verify_org_access(auth, org_id)
    try:
        messages = await db.get_messages(conversation_id)
        return messages
    except Exception as exc:
        logger.error(f"get_conversation_messages failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch messages")


@app.post("/organizations/{org_id}/conversations/{conversation_id}/messages")
async def send_message(
    org_id: str,
    conversation_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Send a message in a conversation and get an AI response.

    Carries context from the last 20 messages in the conversation.
    """
    _verify_org_access(auth, org_id)
    await check_query_limit(org_id, db)
    start_time = time.time()

    # Validate conversation
    conv = await db.get_conversation(conversation_id)
    if not conv or conv.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if auth.user_id and conv.get("user_id") and conv["user_id"] != auth.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get org for system prompt
    org = await db.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org_metadata = org.get("metadata") or {}
    system_prompt = org_metadata.get("system_prompt")
    org_niche = org.get("niche", "general")

    # If conversation has an assistant, use its system_prompt and temperature
    assistant_temperature = request.temperature
    use_rag = request.use_rag
    assistant_id = conv.get("assistant_id")
    if assistant_id:
        assistant = await db.get_assistant(assistant_id)
        if assistant:
            system_prompt = assistant.get("system_prompt") or system_prompt
            assistant_temperature = assistant.get("temperature", request.temperature)
            use_rag = assistant.get("use_rag", request.use_rag)

    try:
        # Save user message
        user_msg = await db.add_message(
            conversation_id=conversation_id,
            role="user",
            content=request.content,
        )

        # Get conversation history (most recent 20 messages for context)
        history = await db.get_recent_messages(conversation_id, limit=20)

        # RAG context
        context: List[Dict[str, Any]] = []
        if use_rag:
            rag = get_rag_system()
            if rag and rag.is_ready():
                context = await rag.retrieve_context(
                    query=request.content, org_id=org_id, top_k=5
                )

        # Build messages array with conversation history
        context_text = (
            "\n\n".join([c.get("content", "") for c in context]) if context else ""
        )
        system_msg = system_prompt or _build_default_system_prompt(org_niche)
        if context_text:
            system_msg += (
                "\n\nUse the following knowledge base context to provide accurate, well-sourced answers. "
                "Prioritize this context over general knowledge:\n" + context_text
            )

        messages = [{"role": "system", "content": system_msg}]
        for msg in history:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Generate response — try fine-tuned model FIRST (privacy mode)
        response_text = None
        privacy_mode = False
        model_id = conv.get("model_id")

        if model_id:
            try:
                model_rec = await db.get_model(model_id)
                if model_rec:
                    m_metrics = model_rec.get("metrics") or {}
                    has_adapter = m_metrics.get("has_adapter", False)
                    adapter_path = model_rec.get("model_path") or m_metrics.get("adapter_path")
                    base_model_key = model_rec.get("base_model", "tinyllama-1.1b")

                    if has_adapter and adapter_path:
                        server = get_model_server()
                        if server and server.is_available():
                            from enterprise.model_trainer import BASE_MODELS
                            base_model_name = BASE_MODELS.get(base_model_key, base_model_key)
                            result = await server.generate(
                                adapter_path=adapter_path,
                                base_model_name=base_model_name,
                                messages=messages,
                                temperature=assistant_temperature,
                            )
                            if result is not None:
                                response_text, gen_metadata = result
                                privacy_mode = True
                                logger.info(
                                    f"Chat answered by fine-tuned model (private): "
                                    f"{gen_metadata.get('tokens_generated', '?')} tokens"
                                )
            except Exception as local_err:
                logger.warning(f"Local model inference failed, falling back to API: {local_err}")

        # Fallback to API if local model unavailable
        if response_text is None:
            api_manager = get_api_manager()
            # Privacy proxy: sanitize messages before sending to external API
            pii_replacements: Dict[str, str] = {}
            try:
                from enterprise.privacy_proxy import get_privacy_proxy
                proxy = get_privacy_proxy()
                org_name = org.get("name", "")
                user_email = auth.user_id  # best we have here
                # Sanitize the user content in the messages list
                sanitized_messages = []
                for m in messages:
                    if m["role"] == "user":
                        sanitized_content, repl = proxy.sanitize_for_api(
                            user_query=m["content"],
                            org_name=org_name,
                            user_name=user_email,
                        )
                        pii_replacements.update(repl)
                        sanitized_messages.append({"role": "user", "content": sanitized_content})
                    else:
                        sanitized_messages.append(m)
            except Exception as priv_exc:
                logger.warning(f"Chat privacy proxy failed (sending original): {priv_exc}")
                sanitized_messages = messages

            # Log privacy audit event for chat
            if pii_replacements:
                try:
                    from enterprise.privacy_proxy import get_privacy_proxy
                    proxy = get_privacy_proxy()
                    audit_event = proxy.build_audit_event(
                        original_query=request.content,
                        sanitized_query=sanitized_messages[-1]["content"] if sanitized_messages else request.content,
                        replacements=pii_replacements,
                        org_id=org_id,
                        user_id=auth.user_id,
                    )
                    await db.log_privacy_audit(audit_event)
                except Exception:
                    pass
            try:
                response_text, api_used = await asyncio.to_thread(
                    api_manager.chat,
                    "openrouter", sanitized_messages, temperature=assistant_temperature, enable_fallback=True,
                )
                # Rehydrate PII back into the response
                if pii_replacements:
                    try:
                        from enterprise.privacy_proxy import get_privacy_proxy
                        proxy = get_privacy_proxy()
                        response_text = proxy.rehydrate_response(response_text, pii_replacements)
                    except Exception as rehy_exc:
                        logger.warning(f"Chat response rehydration failed: {rehy_exc}")
            except Exception as llm_err:
                err_msg = str(llm_err)
                if "API keys configured" in err_msg:
                    raise HTTPException(status_code=503, detail="LLM service unavailable. No API keys are configured on the server.")
                raise HTTPException(status_code=502, detail=f"LLM service error: {err_msg}")

        # Fact-check (optional)
        confidence = 0.8
        fact_check_results: List[Dict[str, Any]] = []
        if request.use_fact_check:
            fc = get_fact_checker()
            if fc and fc.is_ready():
                fact_check_results = await fc.verify_answer(
                    query=request.content, answer=response_text, context=context,
                )
                if fact_check_results:
                    confidence = sum(r.get("confidence", 0) for r in fact_check_results) / len(fact_check_results)

        response_time_ms = int((time.time() - start_time) * 1000)

        # Log query to queries table
        model_id = conv.get("model_id")
        query_log = None
        if model_id:
            query_log = await db.log_query(
                org_id=org_id,
                model_id=model_id,
                query=request.content,
                response_text=response_text,
                confidence=confidence,
                response_time_ms=response_time_ms,
                user_id=auth.user_id,
            )
            # Link query to conversation
            try:
                db.client.table("queries").update(
                    {"conversation_id": conversation_id}
                ).eq("id", query_log["id"]).execute()
            except Exception:
                pass

        # Save assistant message
        assistant_msg = await db.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            query_id=query_log["id"] if query_log else None,
            metadata={
                "confidence": confidence,
                "response_time_ms": response_time_ms,
                "context_used": len(context) > 0,
                "api_used": "plm_private" if privacy_mode else "plm",
                "privacy_mode": privacy_mode,
            },
        )

        # Auto-title: if this is the first user message, generate a title
        if len(history) <= 1:
            title = request.content[:60]
            if len(request.content) > 60:
                title += "..."
            await db.update_conversation(conversation_id, {"title": title})

        # Background: continuous learning + chat auto-training
        learner = get_continuous_learner()
        if learner and model_id:
            background_tasks.add_task(
                learner.process_query,
                org_id=org_id,
                model_id=model_id,
                query=request.content,
                response=response_text,
                confidence=confidence,
            )
            # Also capture for auto-training
            background_tasks.add_task(
                learner.capture_chat_exchange,
                org_id=org_id,
                model_id=model_id,
                user_query=request.content,
                assistant_response=response_text,
                was_private=privacy_mode,
            )

        return {
            "user_message": user_msg,
            "assistant_message": assistant_msg,
            "confidence": confidence,
            "response_time_ms": response_time_ms,
            "context_used": len(context) > 0,
            "privacy_mode": privacy_mode,
            "sources": [c.get("source") for c in context if c.get("source")] if context else [],
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"send_message failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to process message")


@app.post("/organizations/{org_id}/conversations/{conversation_id}/messages/stream")
async def send_message_stream(
    org_id: str,
    conversation_id: str,
    request: SendMessageRequest,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Send a message and stream the AI response via Server-Sent Events.

    Events:
        - type=status: status updates (e.g. "thinking", "generating")
        - type=token: individual text tokens
        - type=done: final metadata (confidence, response_time_ms, sources, message objects)
        - type=error: error details
    """
    from fastapi.responses import StreamingResponse

    _verify_org_access(auth, org_id)
    await check_query_limit(org_id, db)

    # Validate conversation
    conv = await db.get_conversation(conversation_id)
    if not conv or conv.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if auth.user_id and conv.get("user_id") and conv["user_id"] != auth.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get org for system prompt
    org = await db.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org_metadata = org.get("metadata") or {}
    system_prompt = org_metadata.get("system_prompt")
    org_niche = org.get("niche", "general")

    # If conversation has an assistant, use its settings
    assistant_temperature = request.temperature
    use_rag = request.use_rag
    assistant_id = conv.get("assistant_id")
    if assistant_id:
        assistant = await db.get_assistant(assistant_id)
        if assistant:
            system_prompt = assistant.get("system_prompt") or system_prompt
            assistant_temperature = assistant.get("temperature", request.temperature)
            use_rag = assistant.get("use_rag", request.use_rag)

    # Save user message before streaming
    user_msg = await db.add_message(
        conversation_id=conversation_id,
        role="user",
        content=request.content,
    )

    # Get conversation history (most recent 20 messages for context)
    history = await db.get_recent_messages(conversation_id, limit=20)

    # RAG context
    context: List[Dict[str, Any]] = []
    if use_rag:
        rag = get_rag_system()
        if rag and rag.is_ready():
            context = await rag.retrieve_context(
                query=request.content, org_id=org_id, top_k=5
            )

    # Build messages array
    context_text = (
        "\n\n".join([c.get("content", "") for c in context]) if context else ""
    )
    system_msg = system_prompt or _build_default_system_prompt(org_niche)
    if context_text:
        system_msg += (
            "\n\nUse the following knowledge base context to provide accurate, well-sourced answers. "
            "Prioritize this context over general knowledge:\n" + context_text
        )

    chat_messages = [{"role": "system", "content": system_msg}]
    for msg in history:
        if msg["role"] in ("user", "assistant"):
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    start_time = time.time()

    async def event_generator():
        full_response = ""
        privacy_mode = False
        try:
            yield f"data: {json.dumps({'type': 'status', 'content': 'generating'})}\n\n"

            model_id = conv.get("model_id")

            # Try fine-tuned model FIRST (privacy mode)
            if model_id:
                try:
                    model_rec = await db.get_model(model_id)
                    if model_rec:
                        m_metrics = model_rec.get("metrics") or {}
                        has_adapter = m_metrics.get("has_adapter", False)
                        adapter_path = model_rec.get("model_path") or m_metrics.get("adapter_path")
                        base_model_key = model_rec.get("base_model", "tinyllama-1.1b")

                        if has_adapter and adapter_path:
                            server = get_model_server()
                            if server and server.is_available():
                                from enterprise.model_trainer import BASE_MODELS
                                base_model_name = BASE_MODELS.get(base_model_key, base_model_key)
                                result = await server.generate(
                                    adapter_path=adapter_path,
                                    base_model_name=base_model_name,
                                    messages=chat_messages,
                                    temperature=assistant_temperature,
                                )
                                if result is not None:
                                    full_response, _ = result
                                    privacy_mode = True
                                    # Yield entire response as tokens (local model doesn't stream)
                                    # Chunk into ~20 char segments for smooth UI
                                    chunk_size = 20
                                    for i in range(0, len(full_response), chunk_size):
                                        chunk = full_response[i:i + chunk_size]
                                        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                except Exception as local_err:
                    logger.warning(f"Local model streaming failed, falling back to API: {local_err}")

            # Fallback to API streaming if local model unavailable
            if not full_response:
                api_manager = get_api_manager()
                # Privacy proxy: sanitize before sending to external API
                stream_messages = chat_messages
                pii_repl: Dict[str, str] = {}
                try:
                    from enterprise.privacy_proxy import get_privacy_proxy
                    proxy = get_privacy_proxy()
                    org_name = org.get("name", "")
                    sanitized_msgs = []
                    for m in chat_messages:
                        if m["role"] == "user":
                            s_content, repl = proxy.sanitize_for_api(
                                user_query=m["content"], org_name=org_name, user_name="",
                            )
                            pii_repl.update(repl)
                            sanitized_msgs.append({"role": "user", "content": s_content})
                        else:
                            sanitized_msgs.append(m)
                    stream_messages = sanitized_msgs
                except Exception as priv_exc:
                    logger.warning(f"Stream privacy proxy failed (sending original): {priv_exc}")

                gen, api_used = api_manager.chat_stream(
                    "openrouter", stream_messages, temperature=assistant_temperature,
                )

                for token in gen:
                    full_response += token
                    # Rehydrate individual tokens if PII was replaced
                    display_token = token
                    if pii_repl:
                        for placeholder, original in pii_repl.items():
                            if placeholder in display_token:
                                display_token = display_token.replace(placeholder, original)
                    yield f"data: {json.dumps({'type': 'token', 'content': display_token})}\n\n"

                # Rehydrate full response for saving
                if pii_repl:
                    try:
                        from enterprise.privacy_proxy import get_privacy_proxy
                        proxy = get_privacy_proxy()
                        full_response = proxy.rehydrate_response(full_response, pii_repl)
                    except Exception:
                        pass

        except Exception as exc:
            logger.error(f"Streaming failed: {exc}")
            err_msg = str(exc)
            if "API keys configured" in err_msg:
                err_msg = "LLM service unavailable. No API keys are configured on the server."
            if not full_response:
                yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                return

        # Save assistant message and log query
        response_time_ms = int((time.time() - start_time) * 1000)
        confidence = 0.8

        try:
            model_id = conv.get("model_id")
            query_log = None
            if model_id:
                query_log = await db.log_query(
                    org_id=org_id,
                    model_id=model_id,
                    query=request.content,
                    response_text=full_response,
                    confidence=confidence,
                    response_time_ms=response_time_ms,
                    user_id=auth.user_id,
                )
                try:
                    db.client.table("queries").update(
                        {"conversation_id": conversation_id}
                    ).eq("id", query_log["id"]).execute()
                except Exception:
                    pass

            assistant_msg = await db.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                query_id=query_log["id"] if query_log else None,
                metadata={
                    "confidence": confidence,
                    "response_time_ms": response_time_ms,
                    "context_used": len(context) > 0,
                    "api_used": "plm_private" if privacy_mode else "plm",
                    "privacy_mode": privacy_mode,
                },
            )

            # Auto-title
            if len(history) <= 1:
                title = request.content[:60]
                if len(request.content) > 60:
                    title += "..."
                await db.update_conversation(conversation_id, {"title": title})

            # Background: capture chat for auto-learning
            learner = get_continuous_learner()
            if learner and model_id:
                try:
                    await learner.capture_chat_exchange(
                        org_id=org_id,
                        model_id=model_id,
                        user_query=request.content,
                        assistant_response=full_response,
                        was_private=privacy_mode,
                    )
                except Exception:
                    pass  # Don't fail streaming for learning errors

            yield f"data: {json.dumps({'type': 'done', 'content': {'user_message': user_msg, 'assistant_message': assistant_msg, 'confidence': confidence, 'response_time_ms': response_time_ms, 'context_used': len(context) > 0, 'privacy_mode': privacy_mode, 'sources': [c.get('source') for c in context if c.get('source')] if context else []}})}\n\n"

        except Exception as exc:
            logger.error(f"Failed to save streamed message: {exc}")
            yield f"data: {json.dumps({'type': 'error', 'content': 'Response generated but failed to save.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===================================================================
# MODEL PHASE & GPU CONFIG
# ===================================================================

@app.get("/organizations/{org_id}/models/{model_id}/phase")
async def get_model_phase(
    org_id: str,
    model_id: str,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Return current model lifecycle phase info from the phase manager."""
    _verify_org_access(auth, org_id)
    try:
        from enterprise.phase_manager import ModelPhaseManager
        pm = ModelPhaseManager(db)
        phase_info = await pm.get_phase(org_id, model_id)
        return phase_info
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_model_phase failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch model phase")


@app.post("/organizations/{org_id}/models/{model_id}/gpu-config")
async def set_gpu_config(
    org_id: str,
    model_id: str,
    body: GPUConfigRequest,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Store GPU configuration in the model's metrics."""
    _verify_org_access(auth, org_id)
    try:
        model = await db.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        if model.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Model not found")

        # Merge new GPU config into existing metrics
        metrics = model.get("metrics") or {}
        metrics["gpu_backend"] = body.backend
        if body.api_key is not None:
            metrics["gpu_api_key"] = body.api_key
        if body.hf_token is not None:
            metrics["hf_token"] = body.hf_token
        if body.base_model is not None:
            metrics["base_model"] = body.base_model

        await db.update_model_status(model_id, model.get("status", "created"), metrics)

        logger.info(f"GPU config updated for model {model_id} by user {auth.user_id}")

        # Trigger phase advancement now that GPU is configured
        # Call check_and_advance in a loop: collecting → ready_to_train → training
        try:
            from enterprise.phase_manager import ModelPhaseManager
            phase_mgr = ModelPhaseManager(db)
            prev_phase = None
            for _ in range(3):  # max 3 transitions (collecting → ready → training)
                new_phase = await phase_mgr.check_and_advance(org_id, model_id)
                logger.info(f"Phase check after GPU config: model {model_id} -> {new_phase}")
                if new_phase == prev_phase:
                    break  # phase stabilised
                prev_phase = new_phase
        except Exception as phase_exc:
            logger.warning(f"Phase check after GPU config failed: {phase_exc}")

        return {
            "status": "ok",
            "gpu_backend": body.backend,
            "base_model": body.base_model or model.get("base_model", "tinyllama-1.1b"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"set_gpu_config failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save GPU configuration")


@app.get("/organizations/{org_id}/models/{model_id}/accuracy")
async def get_model_accuracy(
    org_id: str,
    model_id: str,
    refresh: bool = False,
    req: Request = None,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get REAL accuracy score for a model (0-100%).
    
    Accuracy is calculated by:
    1. Testing model against domain-specific validation questions
    2. Evaluating response quality using expert criteria
    3. Factoring in training data volume and RAG knowledge
    
    This is NOT a hardcoded value - it's dynamically computed.
    """
    _verify_org_access(auth, org_id)
    try:
        model = await db.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        if model.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Model not found")
        
        org = await db.get_organization(org_id)
        niche = org.get("niche", "general") if org else "general"
        
        # Get or calculate accuracy
        from enterprise.accuracy_scorer import get_accuracy_scorer
        scorer = get_accuracy_scorer()
        
        if scorer:
            result = await scorer.calculate_accuracy(
                org_id=org_id,
                model_id=model_id,
                niche=niche,
                use_cache=not refresh
            )
        else:
            # Fallback: use stored metrics
            metrics = model.get("metrics") or {}
            result = {
                "accuracy": metrics.get("accuracy", 50.0),
                "confidence": metrics.get("accuracy_confidence", 0.5),
                "tests_passed": metrics.get("tests_passed", 0),
                "tests_total": metrics.get("tests_total", 5),
                "calculated_at": metrics.get("accuracy_calculated_at"),
                "cache_hit": False,
            }
        
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_model_accuracy failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to calculate accuracy")


@app.get("/organizations/{org_id}/models/{model_id}/generation-stats")
async def get_generation_stats(
    org_id: str,
    model_id: str,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Return training data count, breakdown by source, and generation rate."""
    _verify_org_access(auth, org_id)
    try:
        model = await db.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        if model.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Model not found")

        # Total count
        total_count = await db.get_training_data_count(org_id, model_id)

        # Breakdown by source — fetch recent training data and aggregate
        training_data = await db.get_training_data(org_id, model_id=model_id, limit=10000)
        source_breakdown: Dict[str, int] = {}
        for entry in training_data:
            meta = entry.get("metadata") or {}
            source = meta.get("source", "unknown")
            # Reclassify: entries with api_used but no source are API-generated
            if source in ("unknown", "continuous_generation") or meta.get("api_used"):
                source = "api_generated"
            source_breakdown[source] = source_breakdown.get(source, 0) + 1

        # Generation rate from phase manager
        from enterprise.phase_manager import ModelPhaseManager
        pm = ModelPhaseManager(db)
        rate_per_hour = await pm._estimate_generation_rate(org_id, model_id)
        examples_today = await pm._get_today_count(org_id, model_id)

        return {
            "total_count": total_count,
            "source_breakdown": source_breakdown,
            "generation_rate_per_hour": rate_per_hour,
            "examples_generated_today": examples_today,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_generation_stats failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch generation stats")


@app.post("/organizations/{org_id}/models/{model_id}/privacy")
async def toggle_privacy_mode(
    org_id: str,
    model_id: str,
    body: TogglePrivacyRequest,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Toggle forced privacy mode for a model.

    When enabled, queries will ONLY use the fine-tuned model (no external API).
    Requires a deployed adapter to be effective.
    """
    _verify_org_access(auth, org_id)
    try:
        model = await db.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        if model.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Model not found")

        metrics = model.get("metrics") or {}
        metrics["privacy_mode_forced"] = body.enabled

        await db.update_model_status(model_id, model.get("status", "ready"), metrics)
        logger.info(f"Privacy mode {'enabled' if body.enabled else 'disabled'} for model {model_id}")
        return {
            "status": "ok",
            "privacy_mode_forced": body.enabled,
            "has_adapter": metrics.get("has_adapter", False),
            "effective": body.enabled and metrics.get("has_adapter", False),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"toggle_privacy_mode failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update privacy mode")


@app.post("/organizations/{org_id}/models/{model_id}/auto-learning")
async def toggle_auto_learning(
    org_id: str,
    model_id: str,
    body: ToggleAutoLearningRequest,
    req: Request,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Toggle automatic learning from chat interactions for a model.

    When enabled (default), every chat interaction is captured as training data.
    When disabled, the model only uses explicitly generated training data.
    """
    _verify_org_access(auth, org_id)
    try:
        model = await db.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        if model.get("organization_id") != org_id:
            raise HTTPException(status_code=404, detail="Model not found")

        metrics = model.get("metrics") or {}
        metrics["auto_learning_enabled"] = body.enabled

        await db.update_model_status(model_id, model.get("status", "ready"), metrics)
        logger.info(f"Auto-learning {'enabled' if body.enabled else 'disabled'} for model {model_id}")
        return {
            "status": "ok",
            "auto_learning_enabled": body.enabled,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"toggle_auto_learning failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update auto-learning")


# ===================================================================
# NOTIFICATIONS
# ===================================================================

class CreateWebhookRequest(BaseModel):
    url: str = Field(..., min_length=1)
    events: List[str] = Field(..., min_items=1)

    @validator("url")
    def validate_webhook_url(cls, v: str) -> str:
        """Block internal/private IPs and require HTTPS in production."""
        from urllib.parse import urlparse
        import ipaddress

        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Webhook URL must use http or https")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Invalid webhook URL: no hostname")

        # Block obviously dangerous hosts
        blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "metadata.google.internal"}
        if hostname.lower() in blocked_hosts:
            raise ValueError("Webhook URL cannot point to localhost or internal services")

        # Block private/reserved IP ranges
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise ValueError("Webhook URL cannot point to private or reserved IP addresses")
        except ValueError as ip_err:
            if "private" in str(ip_err) or "reserved" in str(ip_err) or "loopback" in str(ip_err):
                raise
            # Not an IP address — hostname is fine, continue

        # Block AWS/GCP/Azure metadata endpoints
        if hostname.startswith("169.254.") or hostname == "metadata.google.internal":
            raise ValueError("Webhook URL cannot point to cloud metadata services")

        return v


@app.get("/me/notifications")
async def get_my_notifications(
    unread_only: bool = False,
    limit: int = 50,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Get notifications for the current user."""
    try:
        from enterprise.notifications import NotificationService
        svc = NotificationService(db)
        notifications = await svc.get_notifications(
            user_id=auth.user_id, unread_only=unread_only, limit=limit,
        )
        unread_count = await svc.get_unread_count(auth.user_id)
        return {"notifications": notifications, "unread_count": unread_count}
    except Exception as exc:
        logger.error(f"get_notifications failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch notifications")


@app.post("/me/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Mark a notification as read."""
    try:
        from enterprise.notifications import NotificationService
        svc = NotificationService(db)
        success = await svc.mark_read(notification_id, auth.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"status": "read", "id": notification_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"mark_notification_read failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update notification")


@app.post("/me/notifications/read-all")
async def mark_all_notifications_read(
    auth: AuthContext = Depends(require_auth),
    db: SupabaseClient = Depends(get_db),
):
    """Mark all notifications as read."""
    try:
        from enterprise.notifications import NotificationService
        svc = NotificationService(db)
        count = await svc.mark_all_read(auth.user_id)
        return {"status": "done", "marked_read": count}
    except Exception as exc:
        logger.error(f"mark_all_read failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update notifications")


# ---- Webhooks (admin) ----

@app.get("/organizations/{org_id}/webhooks")
async def list_webhooks(
    org_id: str,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """List webhooks for the organization."""
    _verify_org_access(auth, org_id)
    try:
        response = (
            db.client.table("webhooks")
            .select("id, url, events, status, failure_count, last_triggered_at, created_at")
            .eq("organization_id", org_id)
            .order("created_at", desc=True)
            .execute()
        )
        hooks = response.data or []
        return {"webhooks": hooks, "count": len(hooks)}
    except Exception as exc:
        logger.error(f"list_webhooks failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list webhooks")


@app.post("/organizations/{org_id}/webhooks", status_code=201)
async def create_webhook(
    org_id: str,
    request: CreateWebhookRequest,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Create a webhook for the organization."""
    _verify_org_access(auth, org_id)
    import secrets
    try:
        secret = secrets.token_hex(32)
        row = {
            "organization_id": org_id,
            "url": request.url,
            "events": request.events,
            "secret": secret,
            "status": "active",
        }
        response = db.client.table("webhooks").insert(row).execute()
        hook = response.data[0] if response.data else row
        return {**hook, "signing_secret": secret}
    except Exception as exc:
        logger.error(f"create_webhook failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create webhook")


@app.delete("/organizations/{org_id}/webhooks/{webhook_id}")
async def delete_webhook(
    org_id: str,
    webhook_id: str,
    auth: AuthContext = Depends(require_admin),
    db: SupabaseClient = Depends(get_db),
):
    """Delete a webhook."""
    _verify_org_access(auth, org_id)
    try:
        response = (
            db.client.table("webhooks")
            .delete()
            .eq("id", webhook_id)
            .eq("organization_id", org_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"status": "deleted", "id": webhook_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_webhook failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete webhook")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

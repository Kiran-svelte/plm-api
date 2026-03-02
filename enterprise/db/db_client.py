"""
Supabase Client Configuration
Production-ready Supabase client with all enterprise features
"""

from supabase import create_client, Client
from typing import Optional, Dict, Any, List, Callable, TypeVar
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import logging

T = TypeVar("T")

load_dotenv()

logger = logging.getLogger(__name__)

# Supabase Configuration - loaded from environment only
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL:
    logger.error("SUPABASE_URL not set in environment variables")
if not SUPABASE_SERVICE_ROLE_KEY:
    logger.error("SUPABASE_SERVICE_ROLE_KEY not set in environment variables")


class SupabaseClient:
    """Enterprise Supabase client with multi-tenant support"""

    def __init__(self, use_service_role: bool = True):
        key = SUPABASE_SERVICE_ROLE_KEY if use_service_role else SUPABASE_ANON_KEY
        if not SUPABASE_URL or not key:
            raise ValueError(
                "Supabase URL and key must be set via environment variables "
                "(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY)"
            )
        self.client: Client = create_client(SUPABASE_URL, key)
        self.use_service_role = use_service_role
        logger.info(f"Supabase client initialized (service_role={use_service_role})")

    async def _run(self, fn: Callable[[], T]) -> T:
        """Run a sync Supabase call in a thread to avoid blocking the event loop."""
        return await asyncio.to_thread(fn)

    # Organizations
    async def create_organization(
        self,
        name: str,
        slug: str,
        niche: str,
        tier: str = "professional",
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new organization"""
        metadata = {}
        if system_prompt:
            metadata["system_prompt"] = system_prompt
        else:
            metadata["system_prompt"] = (
                f"You are PLM, a specialized AI assistant with deep expertise in {niche}. "
                f"You provide accurate, well-structured, and expert-level responses in the domain of {niche}. "
                f"Draw on industry best practices, established frameworks, and current knowledge to deliver "
                f"comprehensive answers. Be precise, cite relevant concepts, and adapt your communication "
                f"style to the complexity of each question."
            )

        try:
            def _op():
                response = (
                    self.client.table("organizations")
                    .insert({
                        "name": name,
                        "slug": slug,
                        "niche": niche,
                        "tier": tier,
                        "status": "active",
                        "metadata": metadata,
                    })
                    .execute()
                )
                if not response.data:
                    raise RuntimeError("Insert returned no data for organization")
                return response.data[0]
            result = await self._run(_op)
            logger.info(f"Created organization: {name} ({slug})")
            return result
        except Exception as e:
            logger.error(f"Failed to create organization: {e}")
            raise

    async def update_organization(
        self, org_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update organization details"""
        def _op():
            response = (
                self.client.table("organizations")
                .update(updates)
                .eq("id", org_id)
                .execute()
            )
            return response.data[0] if response.data else {}
        return await self._run(_op)

    async def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Get organization by ID"""
        import asyncio as _aio
        def _fetch():
            response = (
                self.client.table("organizations").select("*").eq("id", org_id).execute()
            )
            return response.data[0] if response.data else None
        return await _aio.to_thread(_fetch)

    async def get_organization_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get organization by slug"""
        def _op():
            response = (
                self.client.table("organizations").select("*").eq("slug", slug).execute()
            )
            return response.data[0] if response.data else None
        return await self._run(_op)

    async def list_organizations(
        self, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all organizations"""
        def _op():
            query = self.client.table("organizations").select("*")
            if status:
                query = query.eq("status", status)
            response = query.execute()
            return response.data
        return await self._run(_op)

    # Users
    async def create_user(
        self, user_id: str, org_id: str, email: str, role: str = "member"
    ) -> Dict[str, Any]:
        """Create a user linked to an organization"""
        def _op():
            response = (
                self.client.table("users")
                .insert({
                    "id": user_id,
                    "organization_id": org_id,
                    "email": email,
                    "role": role,
                })
                .execute()
            )
            if not response.data:
                raise RuntimeError("Insert returned no data for user")
            return response.data[0]
        return await self._run(_op)

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        def _op():
            response = self.client.table("users").select("*").eq("id", user_id).execute()
            return response.data[0] if response.data else None
        return await self._run(_op)

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        def _op():
            response = (
                self.client.table("users").select("*").eq("email", email).execute()
            )
            return response.data[0] if response.data else None
        return await self._run(_op)

    async def list_org_users(self, org_id: str) -> List[Dict[str, Any]]:
        """List all users in an organization"""
        def _op():
            response = (
                self.client.table("users")
                .select("*")
                .eq("organization_id", org_id)
                .execute()
            )
            return response.data
        return await self._run(_op)

    async def update_user_role(self, user_id: str, role: str) -> Dict[str, Any]:
        """Update a user's role"""
        def _op():
            response = (
                self.client.table("users")
                .update({"role": role})
                .eq("id", user_id)
                .execute()
            )
            return response.data[0] if response.data else {}
        return await self._run(_op)

    async def delete_user(self, user_id: str) -> bool:
        """Remove a user"""
        def _op():
            response = (
                self.client.table("users").delete().eq("id", user_id).execute()
            )
            return len(response.data) > 0
        return await self._run(_op)

    # Models
    async def create_model(
        self, org_id: str, name: str, base_model: str = "llama-3.2-3b"
    ) -> Dict[str, Any]:
        """Create a new model for an organization"""
        try:
            def _op():
                response = (
                    self.client.table("models")
                    .insert({
                        "organization_id": org_id,
                        "name": name,
                        "base_model": base_model,
                        "status": "pending",
                        "version": "1.0.0",
                    })
                    .execute()
                )
                if not response.data:
                    raise RuntimeError("Insert returned no data for model")
                return response.data[0]
            result = await self._run(_op)
            logger.info(f"Created model: {name} for org {org_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to create model: {e}")
            raise

    async def update_model_status(
        self, model_id: str, status: str, metrics: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Update model status and metrics"""
        import asyncio as _aio
        data: Dict[str, Any] = {"status": status}
        if metrics:
            data["metrics"] = metrics
        if status == "deployed":
            data["deployed_at"] = datetime.utcnow().isoformat()

        def _update():
            response = (
                self.client.table("models").update(data).eq("id", model_id).execute()
            )
            return response.data[0] if response.data else {}
        result = await _aio.to_thread(_update)
        logger.info(f"Updated model {model_id} status to {status}")
        return result

    async def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get model by ID"""
        import asyncio as _aio
        def _fetch():
            response = self.client.table("models").select("*").eq("id", model_id).execute()
            return response.data[0] if response.data else None
        return await _aio.to_thread(_fetch)

    async def list_models(self, org_id: str) -> List[Dict[str, Any]]:
        """List all models for an organization"""
        import asyncio as _aio
        def _list():
            response = (
                self.client.table("models")
                .select("*")
                .eq("organization_id", org_id)
                .execute()
            )
            return response.data
        return await _aio.to_thread(_list)

    # Training Data
    async def add_training_data(
        self,
        org_id: str,
        model_id: str,
        instruction: str,
        output: str,
        quality_score: float,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Add training data example"""
        try:
            import asyncio as _aio
            def _insert():
                response = (
                    self.client.table("training_data")
                    .insert({
                        "organization_id": org_id,
                        "model_id": model_id,
                        "instruction": instruction,
                        "output": output,
                        "quality_score": quality_score,
                        "validated": quality_score >= 8.0,
                        "metadata": metadata or {},
                    })
                    .execute()
                )
                if not response.data:
                    raise RuntimeError("Insert returned no data for training_data")
                return response.data[0]
            return await _aio.to_thread(_insert)
        except Exception as e:
            logger.error(f"Failed to add training data: {e}")
            raise

    async def get_training_data(
        self, org_id: str, model_id: Optional[str] = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get training data for organization/model"""
        import asyncio as _aio
        def _fetch():
            query = (
                self.client.table("training_data")
                .select("*")
                .eq("organization_id", org_id)
            )
            if model_id:
                query = query.eq("model_id", model_id)
            query = query.limit(limit).order("created_at", desc=True)
            response = query.execute()
            return response.data
        return await _aio.to_thread(_fetch)

    async def get_training_data_count(
        self, org_id: str, model_id: Optional[str] = None
    ) -> int:
        """Get count of training data"""
        import asyncio as _aio
        def _count():
            query = (
                self.client.table("training_data")
                .select("id", count="exact")
                .eq("organization_id", org_id)
            )
            if model_id:
                query = query.eq("model_id", model_id)
            response = query.execute()
            return response.count if response.count is not None else len(response.data or [])
        return await _aio.to_thread(_count)

    # Knowledge Base (RAG)
    async def add_knowledge(
        self,
        org_id: str,
        content: str,
        embedding: List[float],
        source: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Add knowledge base entry with embedding"""
        import asyncio as _aio
        try:
            def _insert():
                response = (
                    self.client.table("knowledge_base")
                    .insert({
                        "organization_id": org_id,
                        "content": content,
                        "embedding": embedding,
                        "source": source,
                        "metadata": metadata or {},
                    })
                    .execute()
                )
                if not response.data:
                    raise RuntimeError("Insert returned no data for knowledge_base")
                return response.data[0]
            return await _aio.to_thread(_insert)
        except Exception as e:
            logger.error(f"Failed to add knowledge: {e}")
            raise

    async def search_knowledge(
        self,
        org_id: str,
        query_embedding: List[float],
        limit: int = 5,
        threshold: float = 0.7,
        query_text: str = "",
    ) -> List[Dict[str, Any]]:
        """Search knowledge base using vector similarity.
        
        Tries the match_knowledge RPC first (requires DB function).
        Falls back to Python-side cosine similarity if RPC doesn't exist.
        All sync Supabase calls are wrapped in asyncio.to_thread.
        """
        import asyncio as _aio

        # Try RPC first (fastest, uses pgvector)
        try:
            def _rpc_search():
                return self.client.rpc(
                    "match_knowledge",
                    {
                        "query_embedding": query_embedding,
                        "match_threshold": threshold,
                        "match_count": limit,
                        "org_id": org_id,
                    },
                ).execute()

            response = await _aio.to_thread(_rpc_search)
            return response.data or []
        except Exception as e:
            error_str = str(e)
            if "could not find" not in error_str.lower() and "404" not in error_str:
                logger.warning(f"Vector search RPC failed unexpectedly: {e}")
                return []
            # match_knowledge function doesn't exist — use Python fallback
            logger.info("match_knowledge RPC not found, using Python cosine similarity fallback")

        # Fallback: fetch KB rows and compute cosine similarity in Python
        # Run entirely in a thread to avoid blocking the event loop
        def _python_cosine_fallback():
            import json as _json
            import numpy as np

            all_rows: list = []

            # Strategy 1: keyword-based pre-filtering using ilike
            if query_text and len(query_text) >= 3:
                keywords = [w for w in query_text.split() if len(w) >= 4][:5]
                for kw in keywords:
                    try:
                        r_kw = (
                            self.client.table("knowledge_base")
                            .select("id,content,embedding,source,metadata")
                            .eq("organization_id", org_id)
                            .ilike("content", f"%{kw}%")
                            .limit(50)
                            .execute()
                        )
                        existing_ids = {r["id"] for r in all_rows}
                        for row in (r_kw.data or []):
                            if row["id"] not in existing_ids:
                                all_rows.append(row)
                    except Exception:
                        pass

            # Strategy 2: most recent entries
            try:
                r1 = (
                    self.client.table("knowledge_base")
                    .select("id,content,embedding,source,metadata")
                    .eq("organization_id", org_id)
                    .order("created_at", desc=True)
                    .limit(100)
                    .execute()
                )
                existing_ids = {r["id"] for r in all_rows}
                for row in (r1.data or []):
                    if row["id"] not in existing_ids:
                        all_rows.append(row)
            except Exception as e:
                logger.warning(f"Cosine fallback recent fetch failed: {e}")

            # Strategy 3: oldest entries (initial seed knowledge)
            try:
                r2 = (
                    self.client.table("knowledge_base")
                    .select("id,content,embedding,source,metadata")
                    .eq("organization_id", org_id)
                    .order("created_at", desc=False)
                    .limit(100)
                    .execute()
                )
                existing_ids = {r["id"] for r in all_rows}
                for row in (r2.data or []):
                    if row["id"] not in existing_ids:
                        all_rows.append(row)
            except Exception as e:
                logger.warning(f"Cosine fallback oldest fetch failed: {e}")

            rows = all_rows
            if not rows:
                return []

            query_vec = np.array(query_embedding, dtype=np.float32)
            query_norm = np.linalg.norm(query_vec)
            if query_norm == 0:
                return []

            scored = []
            for row in rows:
                emb = row.get("embedding")
                if not emb:
                    continue
                if isinstance(emb, str):
                    try:
                        emb = _json.loads(emb)
                    except Exception:
                        continue
                if len(emb) != len(query_embedding):
                    continue
                doc_vec = np.array(emb, dtype=np.float32)
                doc_norm = np.linalg.norm(doc_vec)
                if doc_norm == 0:
                    continue
                sim = float(np.dot(query_vec, doc_vec) / (query_norm * doc_norm))
                if sim >= threshold:
                    scored.append({
                        "id": row.get("id"),
                        "content": row.get("content"),
                        "source": row.get("source"),
                        "metadata": row.get("metadata"),
                        "similarity": round(sim, 4),
                    })

            scored.sort(key=lambda x: x["similarity"], reverse=True)
            results = scored[:limit]
            logger.info(f"Python cosine fallback: {len(results)} results from {len(rows)} candidates (threshold={threshold})")
            return results

        try:
            return await _aio.to_thread(_python_cosine_fallback)
        except Exception as e:
            logger.warning(f"Python cosine similarity fallback failed: {e}")
            return []

    async def log_privacy_audit(self, audit_event: Dict[str, Any]) -> bool:
        """Persist a privacy audit event. Gracefully handles missing table."""
        try:
            def _op():
                self.client.table("privacy_audit").insert(audit_event).execute()
                return True
            return await self._run(_op)
        except Exception as e:
            error_str = str(e).lower()
            if "could not find" in error_str or "404" in error_str or "privacy_audit" in error_str:
                logger.debug("privacy_audit table not found, skipping audit persistence")
            else:
                logger.warning(f"Failed to persist privacy audit: {e}")
            return False

    async def get_knowledge_count(self, org_id: str) -> int:
        """Get count of knowledge base entries"""
        def _op():
            response = (
                self.client.table("knowledge_base")
                .select("id", count="exact")
                .eq("organization_id", org_id)
                .execute()
            )
            return response.count if response.count is not None else len(response.data or [])
        return await self._run(_op)

    async def delete_knowledge(self, knowledge_id: str, org_id: str) -> bool:
        """Delete a knowledge base entry"""
        def _op():
            response = (
                self.client.table("knowledge_base")
                .delete()
                .eq("id", knowledge_id)
                .eq("organization_id", org_id)
                .execute()
            )
            return len(response.data) > 0
        return await self._run(_op)

    # Queries
    async def log_query(
        self,
        org_id: str,
        model_id: str,
        query: str,
        response_text: str,
        confidence: float,
        response_time_ms: int,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a query for continuous learning"""
        import asyncio as _aio
        try:
            data: Dict[str, Any] = {
                "organization_id": org_id,
                "model_id": model_id,
                "query": query,
                "response": response_text,
                "confidence": confidence,
                "response_time_ms": response_time_ms,
            }
            if user_id:
                data["user_id"] = user_id

            def _insert():
                resp = self.client.table("queries").insert(data).execute()
                if not resp.data:
                    raise RuntimeError("Insert returned no data for query")
                return resp.data[0]
            return await _aio.to_thread(_insert)
        except Exception as e:
            logger.error(f"Failed to log query: {e}")
            raise

    async def get_queries(
        self, org_id: str, model_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get query history"""
        def _op():
            query = (
                self.client.table("queries").select("*").eq("organization_id", org_id)
            )
            if model_id:
                query = query.eq("model_id", model_id)
            query = query.limit(limit).order("created_at", desc=True)
            response = query.execute()
            return response.data
        return await self._run(_op)

    # Fact Checks
    async def add_fact_check(
        self,
        query_id: str,
        claim: str,
        verified: bool,
        confidence: float,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add fact check result"""
        try:
            def _op():
                response = (
                    self.client.table("fact_checks")
                    .insert({
                        "query_id": query_id,
                        "claim": claim,
                        "verified": verified,
                        "confidence": confidence,
                        "source": source,
                        "verification_method": "multi-model",
                    })
                    .execute()
                )
                if not response.data:
                    raise RuntimeError("Insert returned no data for fact_check")
                return response.data[0]
            return await self._run(_op)
        except Exception as e:
            logger.error(f"Failed to add fact check: {e}")
            raise

    # Audit Logs
    async def get_audit_logs(
        self, org_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit logs for organization"""
        def _op():
            response = (
                self.client.table("audit_logs")
                .select("*")
                .eq("organization_id", org_id)
                .limit(limit)
                .order("created_at", desc=True)
                .execute()
            )
            return response.data
        return await self._run(_op)

    async def create_audit_log(
        self,
        org_id: str,
        user_id: Optional[str],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an audit log entry"""
        data: Dict[str, Any] = {
            "organization_id": org_id,
            "action": action,
            "resource_type": resource_type,
            "details": details or {},
        }
        if user_id:
            data["user_id"] = user_id
        if resource_id:
            data["resource_id"] = resource_id
        if ip_address:
            data["ip_address"] = ip_address

        def _op():
            response = self.client.table("audit_logs").insert(data).execute()
            if not response.data:
                raise RuntimeError("Insert returned no data for audit_log")
            return response.data[0]
        return await self._run(_op)

    # Training Jobs
    async def create_training_job(
        self, org_id: str, model_id: str, training_config: Dict
    ) -> Dict[str, Any]:
        """Create a training job"""
        try:
            def _op():
                response = (
                    self.client.table("training_jobs")
                    .insert({
                        "organization_id": org_id,
                        "model_id": model_id,
                        "status": "queued",
                        "training_config": training_config,
                    })
                    .execute()
                )
                if not response.data:
                    raise RuntimeError("Insert returned no data for training_job")
                return response.data[0]
            result = await self._run(_op)
            logger.info(f"Created training job for model {model_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to create training job: {e}")
            raise

    async def update_training_job(
        self,
        job_id: str,
        status: str,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update training job status"""
        data: Dict[str, Any] = {"status": status}
        if progress is not None:
            data["progress"] = progress
        if error_message:
            data["error_message"] = error_message
        if status == "running" and progress == 0:
            data["started_at"] = datetime.utcnow().isoformat()
        if status in ("completed", "failed"):
            data["completed_at"] = datetime.utcnow().isoformat()

        def _op():
            response = (
                self.client.table("training_jobs").update(data).eq("id", job_id).execute()
            )
            return response.data[0] if response.data else {}
        return await self._run(_op)

    async def get_training_jobs(
        self, org_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get training jobs for organization"""
        def _op():
            response = (
                self.client.table("training_jobs")
                .select("*")
                .eq("organization_id", org_id)
                .limit(limit)
                .order("created_at", desc=True)
                .execute()
            )
            return response.data
        return await self._run(_op)

    # Statistics
    async def get_organization_stats(self, org_id: str) -> Dict[str, Any]:
        """Get comprehensive organization statistics"""
        try:
            def _op():
                response = (
                    self.client.table("organization_stats")
                    .select("*")
                    .eq("id", org_id)
                    .execute()
                )
                return response.data[0] if response.data else {}
            return await self._run(_op)
        except Exception:
            models = await self.list_models(org_id)
            queries = await self.get_queries(org_id, limit=10000)
            training_data = await self.get_training_data(org_id, limit=10000)
            return {
                "total_models": len(models),
                "deployed_models": len(
                    [m for m in models if m["status"] == "deployed"]
                ),
                "total_queries": len(queries),
                "avg_confidence": (
                    sum(q.get("confidence", 0) for q in queries) / len(queries)
                    if queries
                    else 0
                ),
                "avg_response_time_ms": (
                    sum(q.get("response_time_ms", 0) for q in queries) / len(queries)
                    if queries
                    else 0
                ),
                "total_training_examples": len(training_data),
            }

    async def get_model_metrics(self, model_id: str) -> Dict[str, Any]:
        """Get model performance metrics"""
        try:
            def _op():
                response = (
                    self.client.table("model_metrics")
                    .select("*")
                    .eq("id", model_id)
                    .execute()
                )
                return response.data[0] if response.data else {}
            return await self._run(_op)
        except Exception:
            return {}

    # API Keys
    async def list_api_keys(self, org_id: str) -> List[Dict[str, Any]]:
        """List API keys for organization (excluding hash)"""
        def _op():
            response = (
                self.client.table("api_keys")
                .select("id, name, prefix, status, last_used_at, created_at")
                .eq("organization_id", org_id)
                .order("created_at", desc=True)
                .execute()
            )
            return response.data
        return await self._run(_op)

    # Invitations
    async def create_invitation(
        self,
        org_id: str,
        email: str,
        role: str = "member",
        invited_by: Optional[str] = None,
        token: Optional[str] = None,
        expires_hours: int = 72,
    ) -> Dict[str, Any]:
        """Create an invitation to join an organization."""
        import secrets
        from datetime import timedelta
        if not token:
            token = secrets.token_urlsafe(32)
        expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()
        def _op():
            response = (
                self.client.table("invitations")
                .insert({
                    "organization_id": org_id,
                    "email": email,
                    "role": role,
                    "status": "pending",
                    "invited_by": invited_by,
                    "token": token,
                    "expires_at": expires_at,
                })
                .execute()
            )
            if not response.data:
                raise RuntimeError("Insert returned no data for invitation")
            return response.data[0]
        return await self._run(_op)

    async def get_invitation_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get invitation by token."""
        def _op():
            response = (
                self.client.table("invitations")
                .select("*, organizations(name, niche)")
                .eq("token", token)
                .eq("status", "pending")
                .execute()
            )
            return response.data[0] if response.data else None
        return await self._run(_op)

    async def list_invitations(self, org_id: str) -> List[Dict[str, Any]]:
        """List invitations for an organization."""
        def _op():
            response = (
                self.client.table("invitations")
                .select("*")
                .eq("organization_id", org_id)
                .order("created_at", desc=True)
                .execute()
            )
            return response.data
        return await self._run(_op)

    async def accept_invitation(self, invitation_id: str) -> Dict[str, Any]:
        """Mark an invitation as accepted."""
        def _op():
            response = (
                self.client.table("invitations")
                .update({
                    "status": "accepted",
                    "accepted_at": datetime.utcnow().isoformat(),
                })
                .eq("id", invitation_id)
                .execute()
            )
            return response.data[0] if response.data else {}
        return await self._run(_op)

    async def revoke_invitation(self, invitation_id: str, org_id: str) -> bool:
        """Revoke a pending invitation."""
        def _op():
            response = (
                self.client.table("invitations")
                .update({"status": "revoked"})
                .eq("id", invitation_id)
                .eq("organization_id", org_id)
                .eq("status", "pending")
                .execute()
            )
            return len(response.data) > 0
        return await self._run(_op)

    # Assistants
    async def create_assistant(
        self,
        org_id: str,
        name: str,
        system_prompt: str,
        assistant_type: str = "general",
        description: Optional[str] = None,
        model_id: Optional[str] = None,
        icon: str = "brain",
        temperature: float = 0.7,
        use_rag: bool = True,
        knowledge_categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a specialized assistant."""
        def _op():
            response = (
                self.client.table("assistants")
                .insert({
                    "organization_id": org_id,
                    "name": name,
                    "system_prompt": system_prompt,
                    "assistant_type": assistant_type,
                    "description": description or "",
                    "model_id": model_id,
                    "icon": icon,
                    "temperature": temperature,
                    "use_rag": use_rag,
                    "knowledge_categories": knowledge_categories or [],
                    "status": "active",
                })
                .execute()
            )
            if not response.data:
                raise RuntimeError("Insert returned no data for assistant")
            return response.data[0]
        return await self._run(_op)

    async def list_assistants(self, org_id: str) -> List[Dict[str, Any]]:
        """List assistants for an organization."""
        def _op():
            response = (
                self.client.table("assistants")
                .select("*")
                .eq("organization_id", org_id)
                .eq("status", "active")
                .order("created_at", desc=False)
                .execute()
            )
            return response.data
        return await self._run(_op)

    async def get_assistant(self, assistant_id: str) -> Optional[Dict[str, Any]]:
        """Get assistant by ID."""
        def _op():
            response = (
                self.client.table("assistants")
                .select("*")
                .eq("id", assistant_id)
                .execute()
            )
            return response.data[0] if response.data else None
        return await self._run(_op)

    async def update_assistant(
        self, assistant_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an assistant."""
        updates["updated_at"] = datetime.utcnow().isoformat()
        def _op():
            response = (
                self.client.table("assistants")
                .update(updates)
                .eq("id", assistant_id)
                .execute()
            )
            return response.data[0] if response.data else {}
        return await self._run(_op)

    async def delete_assistant(self, assistant_id: str, org_id: str) -> bool:
        """Soft-delete an assistant."""
        def _op():
            response = (
                self.client.table("assistants")
                .update({"status": "archived", "updated_at": datetime.utcnow().isoformat()})
                .eq("id", assistant_id)
                .eq("organization_id", org_id)
                .execute()
            )
            return len(response.data) > 0
        return await self._run(_op)

    async def create_default_assistants(self, org_id: str, niche: str) -> List[Dict[str, Any]]:
        """Create default assistants for a new organization."""
        defaults = [
            {
                "name": "General Assistant",
                "assistant_type": "general",
                "description": f"Your expert {niche} AI assistant powered by PLM",
                "system_prompt": (
                    f"You are PLM General Assistant, a specialized {niche} AI. You provide clear, "
                    f"accurate, and expert-level answers drawing on deep domain knowledge of {niche}. "
                    f"Use available knowledge base context when relevant. Structure your responses "
                    f"clearly with headings, bullet points, and code blocks when appropriate."
                ),
                "icon": "brain",
                "temperature": 0.7,
            },
            {
                "name": "Research Analyst",
                "assistant_type": "research",
                "description": f"Deep research and analysis powered by PLM",
                "system_prompt": (
                    f"You are PLM Research Analyst, specializing in deep {niche} analysis. "
                    f"Provide thorough, well-structured analysis with clear sections and evidence-based "
                    f"reasoning. Break down complex topics systematically. Cite sources and knowledge base "
                    f"context when available. Distinguish between established facts and analytical inferences."
                ),
                "icon": "search",
                "temperature": 0.3,
            },
            {
                "name": "Creative Writer",
                "assistant_type": "creative",
                "description": f"Content creation and creative writing powered by PLM",
                "system_prompt": (
                    f"You are PLM Creative Writer, crafting compelling content for the {niche} domain. "
                    f"Write engaging, audience-appropriate content that captures attention and drives value. "
                    f"Adapt your tone, style, and complexity to the specific request. Use vivid language, "
                    f"strong structure, and domain-specific terminology naturally."
                ),
                "icon": "sparkle",
                "temperature": 1.0,
            },
        ]
        created = []
        for d in defaults:
            try:
                assistant = await self.create_assistant(
                    org_id=org_id, **d, use_rag=True
                )
                created.append(assistant)
            except Exception as e:
                logger.warning(f"Failed to create default assistant '{d['name']}': {e}")
        return created

    # Conversations
    async def create_conversation(
        self,
        org_id: str,
        user_id: Optional[str] = None,
        model_id: Optional[str] = None,
        title: str = "New Conversation",
        assistant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new conversation"""
        data: Dict[str, Any] = {
            "organization_id": org_id,
            "title": title,
            "status": "active",
        }
        if user_id:
            data["user_id"] = user_id
        if model_id:
            data["model_id"] = model_id
        if assistant_id:
            data["assistant_id"] = assistant_id
        def _op():
            response = self.client.table("conversations").insert(data).execute()
            if not response.data:
                raise RuntimeError("Insert returned no data for conversation")
            return response.data[0]
        return await self._run(_op)

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation by ID"""
        def _op():
            response = (
                self.client.table("conversations")
                .select("*")
                .eq("id", conversation_id)
                .execute()
            )
            return response.data[0] if response.data else None
        return await self._run(_op)

    async def list_conversations(
        self, org_id: str, user_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List conversations for an organization, optionally filtered by user"""
        def _op():
            query = (
                self.client.table("conversations")
                .select("*")
                .eq("organization_id", org_id)
                .eq("status", "active")
            )
            if user_id:
                query = query.eq("user_id", user_id)
            query = query.order("updated_at", desc=True).limit(limit)
            response = query.execute()
            return response.data
        return await self._run(_op)

    async def update_conversation(
        self, conversation_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update conversation (title, status, etc.)"""
        updates["updated_at"] = datetime.utcnow().isoformat()
        def _op():
            response = (
                self.client.table("conversations")
                .update(updates)
                .eq("id", conversation_id)
                .execute()
            )
            return response.data[0] if response.data else {}
        return await self._run(_op)

    async def archive_conversation(self, conversation_id: str) -> bool:
        """Archive a conversation (soft delete)"""
        def _op():
            response = (
                self.client.table("conversations")
                .update({"status": "archived", "updated_at": datetime.utcnow().isoformat()})
                .eq("id", conversation_id)
                .execute()
            )
            return len(response.data) > 0
        return await self._run(_op)

    # Messages
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        query_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Add a message to a conversation"""
        data: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
        }
        if query_id:
            data["query_id"] = query_id
        if metadata:
            data["metadata"] = metadata
        def _op():
            response = self.client.table("messages").insert(data).execute()
            if not response.data:
                raise RuntimeError("Insert returned no data for message")
            # Touch conversation updated_at
            self.client.table("conversations").update(
                {"updated_at": datetime.utcnow().isoformat()}
            ).eq("id", conversation_id).execute()
            return response.data[0]
        return await self._run(_op)

    async def get_messages(
        self, conversation_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get messages for a conversation, ordered oldest-first (for display)."""
        def _op():
            response = (
                self.client.table("messages")
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            return response.data
        return await self._run(_op)

    async def get_recent_messages(
        self, conversation_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get the most recent N messages in chronological order."""
        def _op():
            response = (
                self.client.table("messages")
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(reversed(response.data)) if response.data else []
        return await self._run(_op)

    # Health check
    async def health_check(self) -> bool:
        """Check if Supabase connection is healthy"""
        try:
            def _op():
                self.client.table("organizations").select("count").limit(1).execute()
                return True
            return await self._run(_op)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


# Singleton instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client(use_service_role: bool = True) -> SupabaseClient:
    """Get or create Supabase client singleton"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient(use_service_role=use_service_role)
    return _supabase_client

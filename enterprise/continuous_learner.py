"""
Continuous Learner - Real continuous learning from usage

Learns by updating the RAG knowledge base with high-quality interactions.
"Training" in this system means indexing Q&A pairs into the RAG knowledge base
so they surface as context for future queries -- not fine-tuning a model.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta
from enterprise.db.db_client import get_supabase_client

logger = logging.getLogger(__name__)


class ContinuousLearner:
    """Continuous learning system that learns from usage by updating the RAG
    knowledge base with high-quality interactions."""

    def __init__(self):
        """Initialize continuous learner with lazy RAG system loading."""
        self.db = get_supabase_client()
        self.feedback_threshold = 0.8  # Only learn from high-confidence responses
        self._rag_system = None
        logger.info("Continuous learner initialized")

    def _get_rag(self):
        """Lazy-load the RAG system to avoid circular imports and heavy init
        on startup."""
        if self._rag_system is None:
            from enterprise.rag_system import RAGSystem
            self._rag_system = RAGSystem()
        return self._rag_system

    # ------------------------------------------------------------------
    # Core learning entry points
    # ------------------------------------------------------------------

    async def process_query(
        self,
        org_id: str,
        model_id: str,
        query: str,
        response: str,
        confidence: float,
    ):
        """Process a query interaction for continuous learning.

        When the model's confidence meets or exceeds the threshold the Q&A pair
        is persisted in *both* the training_data table (for record-keeping and
        bulk retraining) and the RAG knowledge base (for immediate retrieval in
        future queries).

        Args:
            org_id: Organization ID.
            model_id: Model ID.
            query: User query text.
            response: Model response text.
            confidence: Response confidence score (0-1).
        """
        try:
            if confidence >= self.feedback_threshold:
                # 1. Persist to training_data table for bookkeeping
                await self.db.add_training_data(
                    org_id=org_id,
                    model_id=model_id,
                    instruction=query,
                    output=response,
                    quality_score=confidence * 10,  # Convert to 0-10 scale
                    metadata={
                        "source": "continuous_learning",
                        "timestamp": datetime.utcnow().isoformat(),
                        "confidence": confidence,
                    },
                )

                # 2. Add to RAG knowledge base -- this is the REAL learning
                await self._add_to_knowledge_base(org_id, query, response)

                logger.info(
                    "High-confidence interaction added to training data and "
                    "knowledge base for model %s (confidence=%.2f)",
                    model_id, confidence,
                )

            # Always evaluate whether a bulk re-index is warranted
            await self._check_retrain_trigger(org_id, model_id)

        except Exception as e:
            logger.error("Failed to process query for learning: %s", e)

    async def process_feedback(
        self,
        query_id: str,
        feedback: str,
        comment: Optional[str] = None,
    ):
        """Process explicit user feedback on a previously logged query.

        Feedback handling:
        - "excellent" -- add to training_data *and* RAG knowledge base.
        - "good"      -- add to training_data only (decent but not strong
                         enough signal to teach from immediately).
        - "bad"       -- create an audit log entry so it can be reviewed and
                         corrected by a human.

        Args:
            query_id: ID of the query row in the ``queries`` table.
            feedback: One of "excellent", "good", or "bad".
            comment: Optional free-text comment from the user.
        """
        try:
            # Retrieve the original query record
            import asyncio as _aio
            def _fetch_query():
                return (
                    self.db.client.table("queries")
                    .select("*")
                    .eq("id", query_id)
                    .execute()
                )
            result = await _aio.to_thread(_fetch_query)
            if not result.data:
                logger.warning("Query %s not found -- skipping feedback", query_id)
                return

            query_data = result.data[0]
            org_id = query_data["organization_id"]
            model_id = query_data["model_id"]
            query_text = query_data["query"]
            response_text = query_data["response"]

            if feedback == "excellent":
                # Highest quality signal -- store everywhere
                await self.db.add_training_data(
                    org_id=org_id,
                    model_id=model_id,
                    instruction=query_text,
                    output=response_text,
                    quality_score=10.0,
                    metadata={
                        "source": "user_feedback",
                        "feedback": feedback,
                        "comment": comment,
                        "query_id": query_id,
                    },
                )

                # Index into RAG knowledge base for immediate retrieval
                await self._add_to_knowledge_base(org_id, query_text, response_text)

                logger.info(
                    "Excellent feedback for query %s -- added to training data "
                    "and knowledge base", query_id,
                )

            elif feedback == "good":
                # Decent signal -- training_data only (no KB promotion)
                await self.db.add_training_data(
                    org_id=org_id,
                    model_id=model_id,
                    instruction=query_text,
                    output=response_text,
                    quality_score=7.0,
                    metadata={
                        "source": "user_feedback",
                        "feedback": feedback,
                        "comment": comment,
                        "query_id": query_id,
                    },
                )
                logger.info(
                    "Good feedback for query %s -- added to training data only",
                    query_id,
                )

            elif feedback == "bad":
                # Flag for human review via the audit log
                await self.db.create_audit_log(
                    org_id=org_id,
                    user_id=query_data.get("user_id"),
                    action="bad_response_flagged",
                    resource_type="query",
                    resource_id=query_id,
                    details={
                        "query": query_text,
                        "response": response_text,
                        "feedback": feedback,
                        "comment": comment,
                        "model_id": model_id,
                        "flagged_at": datetime.utcnow().isoformat(),
                    },
                )
                logger.info(
                    "Bad feedback for query %s -- flagged for review in audit log",
                    query_id,
                )

        except Exception as e:
            logger.error("Failed to process feedback for query %s: %s", query_id, e)

    async def capture_chat_exchange(
        self,
        org_id: str,
        model_id: str,
        user_query: str,
        assistant_response: str,
        was_private: bool = False,
    ):
        """Capture every chat exchange as training data for auto-training.

        Unlike process_query(), this has NO confidence threshold. Chat data is
        inherently validated by user engagement (they continued the conversation).

        Args:
            org_id: Organization ID.
            model_id: Model ID.
            user_query: The user's message.
            assistant_response: The assistant's response.
            was_private: Whether the response came from the fine-tuned model.
        """
        try:
            # Store as training data with user_chat source
            await self.db.add_training_data(
                org_id=org_id,
                model_id=model_id,
                instruction=user_query,
                output=assistant_response,
                quality_score=8.0,  # Chat interactions are user-validated
                metadata={
                    "source": "user_chat",
                    "was_private": was_private,
                    "captured_at": datetime.utcnow().isoformat(),
                },
            )

            # Also add to RAG knowledge base for immediate use
            await self._add_to_knowledge_base(org_id, user_query, assistant_response)

            # Check if phase should advance
            try:
                from enterprise.phase_manager import ModelPhaseManager
                phase_mgr = ModelPhaseManager(self.db)
                await phase_mgr.check_and_advance(org_id, model_id)
            except Exception:
                pass

            logger.debug(
                "Chat exchange captured for auto-training: model=%s, private=%s",
                model_id, was_private,
            )
        except Exception as e:
            logger.error("Failed to capture chat exchange: %s", e)

    # ------------------------------------------------------------------
    # Knowledge base helpers
    # ------------------------------------------------------------------

    async def _add_to_knowledge_base(
        self, org_id: str, query: str, response: str
    ) -> bool:
        """Combine a Q&A pair into a single knowledge entry and index it in
        the RAG system (with embeddings) for immediate retrieval.

        Args:
            org_id: Organization ID.
            query: The user question.
            response: The model answer.

        Returns:
            True if the entry was successfully added.
        """
        rag = self._get_rag()
        content = f"Q: {query}\nA: {response}"
        success = await rag.add_knowledge(
            org_id=org_id,
            content=content,
            source="continuous_learning",
            metadata={
                "type": "learned_qa",
                "learned_at": datetime.utcnow().isoformat(),
            },
        )
        if success:
            logger.debug("Added Q&A to knowledge base for org %s", org_id)
        else:
            logger.warning(
                "Failed to add Q&A to knowledge base for org %s", org_id
            )
        return success

    # ------------------------------------------------------------------
    # Retrain / re-index logic
    # ------------------------------------------------------------------

    async def _check_retrain_trigger(self, org_id: str, model_id: str):
        """Decide whether the knowledge base should be bulk re-indexed with
        all recent training data.

        Triggers:
        1. More than 7 days since the model was last deployed.
        2. 100+ new training examples accumulated in the last 7 days.

        Args:
            org_id: Organization ID.
            model_id: Model ID.
        """
        try:
            model = await self.db.get_model(model_id)
            if not model:
                return

            # Check time since last deployment
            last_deployed = model.get("deployed_at")
            if last_deployed:
                last_deployed_date = datetime.fromisoformat(
                    last_deployed.replace("Z", "+00:00")
                )
                days_since_deploy = (
                    datetime.utcnow() - last_deployed_date.replace(tzinfo=None)
                ).days

                if days_since_deploy >= 7:
                    await self._trigger_retrain(org_id, model_id, "scheduled_weekly")
                    return

            # Check volume of new training data
            cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
            import asyncio as _aio
            def _count_new():
                return (
                    self.db.client.table("training_data")
                    .select("id", count="exact")
                    .eq("organization_id", org_id)
                    .eq("model_id", model_id)
                    .gte("created_at", cutoff)
                    .execute()
                )
            response = await _aio.to_thread(_count_new)
            new_examples_count = response.count if response.count is not None else len(response.data or [])

            if new_examples_count >= 100:
                await self._trigger_retrain(org_id, model_id, "new_data_threshold")

        except Exception as e:
            logger.error("Failed to check retrain trigger: %s", e)

    async def _trigger_retrain(self, org_id: str, model_id: str, reason: str):
        """Trigger a "retrain" -- which in our system means bulk-indexing all
        recent training data into the RAG knowledge base.

        Steps:
        1. Create a training job record for auditing.
        2. Mark the job as running.
        3. Fetch all training data for the org/model.
        4. Index every example into the knowledge base via the RAG system.
        5. Update the model status to reflect the re-index.
        6. Mark the training job as completed (or failed).

        Args:
            org_id: Organization ID.
            model_id: Model ID.
            reason: Human-readable reason for the retrain.
        """
        job = None
        try:
            # 1. Create training job
            job = await self.db.create_training_job(
                org_id=org_id,
                model_id=model_id,
                training_config={
                    "trigger": "continuous_learning",
                    "reason": reason,
                    "auto_triggered": True,
                    "started_at": datetime.utcnow().isoformat(),
                },
            )
            if not job or "id" not in job:
                raise ValueError("Failed to create training job - no ID returned")
            job_id = job["id"]

            # 2. Mark as running
            await self.db.update_training_job(job_id, status="running", progress=0)

            # 3. Fetch all training data for this org/model
            training_data = await self.db.get_training_data(
                org_id, model_id=model_id, limit=1000
            )

            if not training_data:
                await self.db.update_training_job(
                    job_id, status="completed", progress=1.0
                )
                logger.info(
                    "Retrain for model %s skipped -- no training data", model_id
                )
                return

            # 4. Index into knowledge base via RAG
            rag = self._get_rag()
            indexed_count = await rag.add_from_training_data(org_id, training_data)

            # 5. Update model status/metrics to reflect re-index
            await self.db.update_model_status(
                model_id,
                status="deployed",
                metrics={
                    "last_retrain_reason": reason,
                    "last_retrain_at": datetime.utcnow().isoformat(),
                    "training_examples_indexed": indexed_count,
                    "total_training_examples": len(training_data),
                },
            )

            # 6. Mark job as completed
            await self.db.update_training_job(job_id, status="completed", progress=1.0)

            logger.info(
                "Retrain completed for model %s. Reason: %s. "
                "Indexed %d entries into knowledge base.",
                model_id, reason, indexed_count,
            )

        except Exception as e:
            logger.error("Failed to trigger retrain for model %s: %s", model_id, e)
            if job:
                try:
                    await self.db.update_training_job(
                        job["id"], status="failed", error_message=str(e)
                    )
                except Exception as inner:
                    logger.error("Failed to mark training job as failed: %s", inner)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    async def get_learning_stats(
        self, org_id: str, model_id: str
    ) -> Dict[str, Any]:
        """Return continuous-learning statistics including knowledge base
        metrics.

        Args:
            org_id: Organization ID.
            model_id: Model ID.

        Returns:
            Dictionary of learning statistics.
        """
        try:
            # Training data stats
            import asyncio as _aio
            def _fetch_stats():
                return (
                    self.db.client.table("training_data")
                    .select("*")
                    .eq("organization_id", org_id)
                    .eq("model_id", model_id)
                    .execute()
                )
            response = await _aio.to_thread(_fetch_stats)
            training_data = response.data or []

            total_examples = len(training_data)
            from_learning = len([
                d for d in training_data
                if d.get("metadata", {}).get("source") == "continuous_learning"
            ])
            from_feedback = len([
                d for d in training_data
                if d.get("metadata", {}).get("source") == "user_feedback"
            ])
            avg_quality = (
                sum(d.get("quality_score", 0) for d in training_data) / total_examples
                if total_examples > 0 else 0
            )

            # Knowledge base stats from RAG system
            rag = self._get_rag()
            kb_stats = await rag.get_knowledge_stats(org_id)

            return {
                "total_training_examples": total_examples,
                "from_continuous_learning": from_learning,
                "from_user_feedback": from_feedback,
                "average_quality_score": round(avg_quality, 2),
                "knowledge_base": kb_stats,
                "learning_enabled": True,
                "feedback_threshold": self.feedback_threshold,
            }

        except Exception as e:
            logger.error("Failed to get learning stats: %s", e)
            return {"error": str(e)}

    async def export_learned_data(
        self,
        org_id: str,
        model_id: str,
        since_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Export training data collected via continuous learning over the
        specified window.

        Args:
            org_id: Organization ID.
            model_id: Model ID.
            since_days: Number of days to look back (default 7).

        Returns:
            List of training data rows.
        """
        try:
            since_date = (datetime.utcnow() - timedelta(days=since_days)).isoformat()

            import asyncio as _aio
            def _fetch_export():
                return (
                    self.db.client.table("training_data")
                    .select("*")
                    .eq("organization_id", org_id)
                    .eq("model_id", model_id)
                    .gte("created_at", since_date)
                    .order("created_at", desc=True)
                    .execute()
                )
            response = await _aio.to_thread(_fetch_export)

            return response.data or []

        except Exception as e:
            logger.error("Failed to export learned data: %s", e)
            return []

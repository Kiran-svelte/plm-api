"""
RAG System - Solving GAP 1 (Hallucination) and GAP 7 (Context Limits)

Provides unlimited context through vector-based retrieval
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import List, Dict, Any, Optional
import numpy as np
import logging
import httpx
from enterprise.db.db_client import get_supabase_client

logger = logging.getLogger(__name__)

# Try to import sentence_transformers, fallback to API if not available
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence_transformers not available, will use HF Inference API for embeddings")


class RAGSystem:
    """Retrieval Augmented Generation System"""

    def __init__(self, model_name: str = None):
        """
        Initialize RAG system with embedding model

        Args:
            model_name: HuggingFace model for embeddings.
                        Defaults to all-mpnet-base-v2 (768 dims) to match Supabase schema.
                        Use all-MiniLM-L6-v2 (384 dims) only if DB supports it.
        """
        # Default to 768-dim model to match Supabase knowledge_base table
        if model_name is None:
            model_name = os.environ.get("RAG_EMBEDDING_MODEL", "all-mpnet-base-v2")
        
        self.model_name = model_name
        self.embedding_dim = 768  # Default for all-mpnet-base-v2
        self.use_api = False
        self.hf_api_key = os.environ.get("HF_API_KEY", "")
        
        # Try local model first, fallback to HF Inference API
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer(model_name)
                self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
                self.ready = True
                logger.info(f"RAG system initialized with local {model_name} ({self.embedding_dim} dims)")
            except Exception as e:
                logger.warning(f"Failed to load local model: {e}, trying HF Inference API")
                self._init_api_fallback()
        else:
            self._init_api_fallback()
    
    def _init_api_fallback(self):
        """Initialize HuggingFace Inference API fallback for embeddings"""
        if self.hf_api_key:
            self.use_api = True
            self.ready = True
            # Map model name to HF model ID for Inference API
            self.hf_model_id = f"sentence-transformers/{self.model_name}"
            logger.info(f"RAG system using HF Inference API with {self.hf_model_id}")
        else:
            self.ready = False
            logger.error("RAG system failed: no local model and no HF_API_KEY for API fallback")

    def is_ready(self) -> bool:
        """Check if RAG system is ready"""
        return self.ready

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        if not self.ready:
            return []

        try:
            if self.use_api:
                return self._generate_embedding_via_api(text)
            else:
                embedding = self.embedding_model.encode(text)
                return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []
    
    def _generate_embedding_via_api(self, text: str) -> List[float]:
        """Generate embedding using HuggingFace Inference API"""
        try:
            url = f"https://api-inference.huggingface.co/models/{self.hf_model_id}"
            headers = {"Authorization": f"Bearer {self.hf_api_key}"}
            
            response = httpx.post(
                url,
                headers=headers,
                json={"inputs": text, "options": {"wait_for_model": True}},
                timeout=30.0
            )
            
            if response.status_code == 200:
                embedding = response.json()
                if isinstance(embedding, list) and len(embedding) > 0:
                    # HF returns [[...embedding...]] for single input
                    if isinstance(embedding[0], list):
                        return embedding[0]
                    return embedding
                logger.error(f"Unexpected HF API response format: {type(embedding)}")
                return []
            else:
                logger.error(f"HF API error {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            logger.error(f"HF API embedding error: {e}")
            return []


    async def add_knowledge(
        self,
        org_id: str,
        content: str,
        source: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Add knowledge to organization's knowledge base

        Args:
            org_id: Organization ID
            content: Knowledge content
            source: Source of knowledge
            metadata: Additional metadata

        Returns:
            Success status
        """
        if not self.ready:
            logger.warning("RAG system not ready, cannot add knowledge")
            return False

        try:
            # Generate embedding (in thread to avoid blocking event loop)
            import asyncio as _aio
            embedding = await _aio.to_thread(self.generate_embedding, content)
            if not embedding:
                return False

            # Store in database
            db = get_supabase_client()
            await db.add_knowledge(
                org_id=org_id,
                content=content,
                embedding=embedding,
                source=source,
                metadata=metadata
            )

            logger.info(f"Added knowledge for org {org_id}: {content[:100]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to add knowledge: {e}")
            return False

    async def retrieve_context(
        self,
        query: str,
        org_id: str,
        top_k: int = 5,
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for query using vector similarity

        Args:
            query: User query
            org_id: Organization ID
            top_k: Number of results to return
            threshold: Similarity threshold

        Returns:
            List of relevant knowledge entries with scores
        """
        if not self.ready:
            logger.warning("RAG system not ready, returning empty context")
            return []

        try:
            # Generate query embedding (in thread to avoid blocking event loop)
            import asyncio as _aio
            query_embedding = await _aio.to_thread(self.generate_embedding, query)
            if not query_embedding:
                return []

            # Search knowledge base
            db = get_supabase_client()
            results = await db.search_knowledge(
                org_id=org_id,
                query_embedding=query_embedding,
                limit=top_k,
                threshold=threshold,
                query_text=query,
            )

            logger.info(f"Retrieved {len(results)} context items for query: {query[:100]}")
            return results
        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            return []

    async def initialize_org_knowledge(
        self,
        org_id: str,
        niche: str,
        base_knowledge: Optional[List[str]] = None
    ) -> bool:
        """
        Initialize knowledge base for new organization

        Args:
            org_id: Organization ID
            niche: Organization niche
            base_knowledge: Optional list of base knowledge texts

        Returns:
            Success status
        """
        try:
            # Add niche-specific base knowledge
            niche_knowledge = self._get_niche_base_knowledge(niche)

            for knowledge in niche_knowledge:
                await self.add_knowledge(
                    org_id=org_id,
                    content=knowledge,
                    source="system_initialization",
                    metadata={"niche": niche, "type": "base"}
                )

            # Add custom base knowledge if provided
            if base_knowledge:
                for knowledge in base_knowledge:
                    await self.add_knowledge(
                        org_id=org_id,
                        content=knowledge,
                        source="customer_provided",
                        metadata={"niche": niche, "type": "custom"}
                    )

            logger.info(f"Initialized knowledge base for org {org_id} in {niche} niche")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize org knowledge: {e}")
            return False

    def _get_niche_base_knowledge(self, niche: str) -> List[str]:
        """Get base knowledge for specific niche"""
        # In production, this would be a comprehensive knowledge base
        # For now, return basic template knowledge

        base_knowledge_templates = {
            "healthcare": [
                "HIPAA (Health Insurance Portability and Accountability Act) is a federal law protecting sensitive patient health information.",
                "Medical diagnosis requires thorough patient history, physical examination, and appropriate diagnostic tests.",
                "Electronic Health Records (EHR) systems must maintain confidentiality, integrity, and availability of patient data.",
            ],
            "cryptocurrency": [
                "Blockchain is a distributed ledger technology that records transactions across multiple computers.",
                "Cryptocurrency trading involves buying and selling digital assets on exchanges.",
                "DeFi (Decentralized Finance) enables financial services without traditional intermediaries.",
            ],
            "legal": [
                "Contract law governs legally binding agreements between parties.",
                "Due diligence is the investigation of a business prior to signing a contract.",
                "Legal compliance requires adherence to applicable laws and regulations.",
            ],
            "finance": [
                "Risk management involves identifying, assessing, and prioritizing risks.",
                "Portfolio diversification reduces risk by spreading investments across different assets.",
                "Financial regulations protect investors and maintain market integrity.",
            ]
        }

        # Try to match niche (case-insensitive)
        niche_lower = niche.lower()
        for key, knowledge in base_knowledge_templates.items():
            if key in niche_lower:
                return knowledge

        # Default: generic knowledge
        return [
            f"{niche} requires specialized domain expertise and continuous learning.",
            f"Best practices in {niche} evolve with industry developments and technological advances.",
            f"Professionals in {niche} must stay updated with the latest trends and regulations.",
        ]

    async def add_from_training_data(
        self,
        org_id: str,
        training_examples: List[Dict[str, Any]]
    ) -> int:
        """
        Add training data to knowledge base for RAG.

        Combines each Q+A pair into a single knowledge entry so that
        the answer retains its question context for better retrieval.

        Args:
            org_id: Organization ID
            training_examples: List of training examples (instruction + output)

        Returns:
            Number of examples added
        """
        count = 0
        for example in training_examples:
            instruction = example.get("instruction", "")
            output = example.get("output", "")
            if not instruction or not output:
                continue

            # Combine Q+A into a single coherent knowledge entry
            combined = f"Q: {instruction}\n\nA: {output}"
            success = await self.add_knowledge(
                org_id=org_id,
                content=combined,
                source="training_data",
                metadata={"type": "qa_pair", **example.get("metadata", {})}
            )
            if success:
                count += 1

        logger.info(f"Added {count} knowledge entries from training data")
        return count

    async def get_knowledge_stats(self, org_id: str) -> Dict[str, Any]:
        """Get knowledge base statistics for organization"""
        try:
            db = get_supabase_client()
            response = db.client.table("knowledge_base")\
                .select("id", count="exact")\
                .eq("organization_id", org_id)\
                .execute()

            return {
                "total_entries": response.count if response.count is not None else len(response.data or []),
                "embedding_dim": self.embedding_dim,
                "ready": self.ready
            }
        except Exception as e:
            logger.error(f"Failed to get knowledge stats: {e}")
            return {"error": str(e)}

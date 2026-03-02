"""
PLM Continuous Data Generator
Generates training data 24/7 using free APIs (Groq/SambaNova/Gemini).
Spreads calls across APIs to maximize throughput via separate rate limit pools.

Strategy:
  - Questions via Groq (~30 req/min)
  - Answers via SambaNova (separate rate limit pool)
  - Validation via Gemini (separate rate limit pool)
  - Effective: ~10 examples/min = ~600/hr = ~5,000-10,000/day

Auto-starts on org creation. Pauses during active training.
"""

import os
import random
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Diverse question types for rich training data
QUESTION_TYPES = [
    "factual",       # "What is X?"
    "explanatory",   # "Explain how X works"
    "comparison",    # "Compare X and Y"
    "scenario",      # "What would happen if...?"
    "best_practice", # "What's the best approach for...?"
    "troubleshoot",  # "How to solve problem X?"
    "deep_dive",     # "Provide an in-depth analysis of..."
    "practical",     # "Step-by-step guide for..."
    "edge_case",     # "What are the edge cases for...?"
    "opinion",       # "What are the pros and cons of...?"
]

# Niche-specific topic seeds
NICHE_TOPICS: Dict[str, List[str]] = {
    "healthcare": [
        "clinical diagnosis", "patient treatment protocols", "HIPAA compliance",
        "electronic health records", "telemedicine", "pharmaceutical interactions",
        "medical imaging analysis", "clinical trial design", "patient safety",
        "healthcare AI applications", "mental health assessment", "surgical procedures",
        "emergency medicine", "preventive care strategies", "medical coding and billing",
    ],
    "legal": [
        "contract law", "intellectual property", "regulatory compliance",
        "litigation strategy", "due diligence", "corporate governance",
        "employment law", "data privacy regulations", "merger and acquisition",
        "dispute resolution", "legal risk assessment", "statutory interpretation",
        "international trade law", "real estate transactions", "securities law",
    ],
    "finance": [
        "risk management", "portfolio optimization", "financial modeling",
        "regulatory frameworks (SEC/FINRA)", "corporate valuation", "derivatives pricing",
        "credit analysis", "asset allocation", "financial statements analysis",
        "investment banking", "private equity", "venture capital due diligence",
        "tax planning strategies", "ESG investing", "quantitative trading",
    ],
    "crypto": [
        "DeFi protocols", "smart contract security", "tokenomics design",
        "blockchain consensus mechanisms", "NFT marketplace dynamics",
        "yield farming strategies", "cross-chain bridges", "on-chain analytics",
        "crypto regulatory landscape", "DAO governance", "layer 2 scaling solutions",
        "stablecoin mechanics", "MEV extraction", "crypto wallet security",
        "token launch strategies",
    ],
    "technology": [
        "system architecture", "cloud infrastructure (AWS/GCP/Azure)",
        "microservices design", "database optimization", "API design patterns",
        "CI/CD pipelines", "containerization (Docker/K8s)", "security best practices",
        "performance optimization", "distributed systems", "machine learning deployment",
        "frontend frameworks", "backend scalability", "DevOps automation",
        "monitoring and observability",
    ],
    "devtools": [
        "SDK design principles", "CLI tool architecture", "API versioning",
        "developer experience (DX)", "documentation best practices",
        "testing frameworks", "code review automation", "IDE extensions",
        "package management", "build systems", "debugging tooling",
        "developer onboarding", "API gateway design", "webhook patterns",
        "developer analytics",
    ],
    "education": [
        "curriculum design", "learning assessment methods", "educational technology",
        "adaptive learning systems", "student engagement strategies",
        "online course design", "pedagogical frameworks", "formative assessment",
        "differentiated instruction", "education policy analysis",
        "STEM education", "special education strategies", "gamification in learning",
        "teacher professional development", "education data analytics",
    ],
    "marketing": [
        "content marketing strategy", "SEO optimization", "social media marketing",
        "conversion rate optimization", "email marketing automation",
        "brand development", "influencer marketing", "PPC advertising",
        "marketing analytics", "customer journey mapping",
        "growth hacking", "product marketing", "B2B marketing strategy",
        "video marketing", "community building",
    ],
    "real_estate": [
        "property valuation", "market analysis", "investment analysis",
        "zoning regulations", "commercial real estate", "property management",
        "real estate finance", "development feasibility", "lease negotiation",
        "REIT analysis", "property tax assessment", "construction management",
        "real estate technology", "sustainable building practices",
        "real estate syndication",
    ],
}


def _get_topics_for_niche(niche: str) -> List[str]:
    """Get topic list for a niche, falling back to generic generation."""
    niche_lower = niche.lower().strip()
    # Direct match
    if niche_lower in NICHE_TOPICS:
        return NICHE_TOPICS[niche_lower]
    # Partial match
    for key, topics in NICHE_TOPICS.items():
        if key in niche_lower or niche_lower in key:
            return topics
    # Generic fallback
    return [
        f"fundamentals of {niche}",
        f"advanced {niche} techniques",
        f"best practices in {niche}",
        f"common mistakes in {niche}",
        f"{niche} industry trends",
        f"{niche} tools and frameworks",
        f"{niche} case studies",
        f"troubleshooting {niche} problems",
        f"{niche} strategy and planning",
        f"emerging innovations in {niche}",
    ]


class ContinuousDataGenerator:
    """Generates training data continuously using free LLM APIs."""

    def __init__(self):
        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._api_manager = None
        self._db = None

    def _get_api_manager(self):
        if self._api_manager is None:
            from src.generators.free_api_clients import FreeAPIManager
            self._api_manager = FreeAPIManager()
        return self._api_manager

    def _get_db(self):
        if self._db is None:
            from enterprise.db.db_client import get_supabase_client
            self._db = get_supabase_client(use_service_role=True)
        return self._db

    async def start_for_org(self, org_id: str, model_id: str):
        """Start continuous generation for an organization's model."""
        key = f"{org_id}:{model_id}"
        if key in self._tasks and not self._tasks[key].done():
            logger.info(f"Generator already running for {key}")
            return

        self._running = True
        task = asyncio.create_task(self._generation_loop(org_id, model_id))
        self._tasks[key] = task
        logger.info(f"Started continuous generation for org {org_id}, model {model_id}")

    async def stop_for_org(self, org_id: str, model_id: str):
        """Stop generation for an organization."""
        key = f"{org_id}:{model_id}"
        if key in self._tasks:
            self._tasks[key].cancel()
            del self._tasks[key]
            logger.info(f"Stopped generation for {key}")

    def is_running(self, org_id: str, model_id: str) -> bool:
        """Check if generator is running for an org."""
        key = f"{org_id}:{model_id}"
        return key in self._tasks and not self._tasks[key].done()

    async def _generation_loop(self, org_id: str, model_id: str):
        """Main generation loop - runs continuously."""
        db = self._get_db()

        try:
            org = await db.get_organization(org_id)
            if not org:
                logger.error(f"Org {org_id} not found, stopping generator")
                return

            niche = org["niche"]
            topics = _get_topics_for_niche(niche)
            custom_topics = org.get("metadata", {}).get("topics", [])
            if custom_topics:
                topics = list(set(topics + custom_topics))

            logger.info(
                f"Generator loop started: niche={niche}, "
                f"{len(topics)} topics, org={org_id}"
            )

            consecutive_errors = 0

            while self._running:
                try:
                    # Check current phase — pause during training
                    from enterprise.phase_manager import ModelPhaseManager
                    phase_mgr = ModelPhaseManager(db)
                    phase_info = await phase_mgr.get_phase(org_id, model_id)

                    if phase_info.get("phase") == "training":
                        logger.info(f"Model {model_id} is training, pausing generation")
                        await asyncio.sleep(60)
                        continue

                    # Pick random topic and question type
                    topic = random.choice(topics)
                    q_type = random.choice(QUESTION_TYPES)

                    # Generate one example
                    example = await self._generate_one_example(niche, topic, q_type)

                    if example:
                        # Save to training_data
                        await db.add_training_data(
                            org_id=org_id,
                            model_id=model_id,
                            instruction=example["instruction"],
                            output=example["output"],
                            quality_score=example["quality_score"],
                            metadata={
                                "niche": niche,
                                "topic": topic,
                                "question_type": q_type,
                                "source": "continuous_generation",
                            },
                        )

                        # Add to RAG knowledge base
                        try:
                            from enterprise.rag_system import RAGSystem
                            rag = RAGSystem()
                            if rag.is_ready():
                                await rag.add_from_training_data(org_id, [example])
                        except Exception as rag_err:
                            logger.debug(f"RAG indexing skipped: {rag_err}")

                        # Check phase advancement
                        await phase_mgr.check_and_advance(org_id, model_id)

                        consecutive_errors = 0
                        logger.debug(
                            f"Generated example for {org_id}: "
                            f"topic={topic}, type={q_type}, "
                            f"score={example['quality_score']}"
                        )

                    # Rate limiting: ~2-3 seconds between attempts
                    # 3 API calls per example across different providers
                    await asyncio.sleep(random.uniform(2.0, 3.5))

                except asyncio.CancelledError:
                    logger.info(f"Generator cancelled for org {org_id}")
                    return
                except Exception as e:
                    consecutive_errors += 1
                    backoff = min(60, 5 * consecutive_errors)
                    logger.error(
                        f"Generation error #{consecutive_errors} for org {org_id}: {e}. "
                        f"Backing off {backoff}s"
                    )
                    await asyncio.sleep(backoff)

                    # Stop after 20 consecutive errors
                    if consecutive_errors >= 20:
                        logger.error(
                            f"Too many errors for org {org_id}, stopping generator"
                        )
                        return

        except asyncio.CancelledError:
            logger.info(f"Generator cancelled for org {org_id}")
        except Exception as exc:
            logger.error(f"Generator loop crashed for org {org_id}: {exc}")

    async def _generate_one_example(
        self, niche: str, topic: str, q_type: str
    ) -> Optional[Dict[str, Any]]:
        """Generate a single Q&A training example.

        Uses different API providers for each step to maximize throughput:
        - Question generation: Groq (fastest)
        - Answer generation: SambaNova (separate rate limit)
        - Quality validation: Gemini (separate rate limit)
        """
        api = self._get_api_manager()

        # Step 1: Generate question (prefer Groq)
        question = await self._call_api(
            api,
            preferred="groq",
            messages=[{
                "role": "user",
                "content": (
                    f"Generate a {q_type} question that a {niche} professional would ask "
                    f"about {topic}. The question should be specific, practical, and require "
                    f"expert-level knowledge to answer properly.\n\n"
                    f"Return ONLY the question, nothing else."
                ),
            }],
            temperature=0.9,
            max_tokens=200,
        )
        if not question or len(question.strip()) < 10:
            return None

        question = question.strip().strip('"')

        # Step 2: Generate comprehensive answer (prefer SambaNova)
        answer = await self._call_api(
            api,
            preferred="sambanova",
            messages=[{
                "role": "user",
                "content": (
                    f"You are a world-class expert in {niche}, specifically in {topic}. "
                    f"Provide a comprehensive, accurate, and detailed answer to this question. "
                    f"Use proper terminology, cite relevant frameworks or standards where "
                    f"applicable, and structure your response clearly with headings or bullet "
                    f"points if appropriate. Aim for 300-500 words.\n\n"
                    f"Question: {question}"
                ),
            }],
            temperature=0.7,
            max_tokens=2000,
        )
        if not answer or len(answer.strip()) < 50:
            return None

        answer = answer.strip()

        # Step 3: Validate quality (prefer Gemini)
        score_text = await self._call_api(
            api,
            preferred="gemini",
            messages=[{
                "role": "user",
                "content": (
                    f"Rate the quality of this Q&A pair for training a {niche} AI on a "
                    f"scale of 1-10. Consider accuracy, completeness, clarity, and "
                    f"professional depth.\n\n"
                    f"Question: {question}\n\n"
                    f"Answer: {answer}\n\n"
                    f"Return ONLY a number between 1 and 10."
                ),
            }],
            temperature=0.3,
            max_tokens=10,
        )

        try:
            score = float(score_text.strip().split()[0])
            score = max(1.0, min(10.0, score))
        except (ValueError, IndexError):
            score = 7.0  # Default if parsing fails

        if score < 7.0:
            return None

        return {
            "instruction": question,
            "output": answer,
            "quality_score": score,
            "metadata": {
                "niche": niche,
                "topic": topic,
                "question_type": q_type,
                "source": "continuous_generation",
            },
        }

    async def _call_api(
        self, api_manager, preferred: str,
        messages: list, temperature: float = 0.7, max_tokens: int = 4000
    ) -> Optional[str]:
        """Call an LLM API with preferred provider and fallback."""
        try:
            response, _ = await asyncio.to_thread(
                api_manager.chat,
                preferred,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_fallback=True,
            )
            return response
        except Exception as e:
            logger.warning(f"API call failed (preferred={preferred}): {e}")
            return None

    async def resume_all_active(self):
        """Resume generation for all active organizations.
        Called on server startup to restart generators that were running.
        """
        db = self._get_db()
        try:
            # Query all orgs (status column may not exist on all deployments)
            orgs = await db.list_organizations()
            resumed = 0
            for org in orgs:
                org_id = org["id"]
                models = await db.list_models(org_id)
                for model in models:
                    metrics = model.get("metrics") or {}
                    phase = metrics.get("phase", "collecting")
                    # Resume generation for models in collecting or learning phase
                    if phase in ("collecting", "learning", "ready_to_train"):
                        await self.start_for_org(org_id, model["id"])
                        resumed += 1
            logger.info(f"Resumed data generation for {resumed} model(s)")
        except Exception as exc:
            logger.error(f"Failed to resume generators: {exc}")


# Singleton
_generator_instance: Optional[ContinuousDataGenerator] = None


def get_data_generator() -> ContinuousDataGenerator:
    """Get or create the singleton data generator."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ContinuousDataGenerator()
    return _generator_instance

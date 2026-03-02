"""
Pet Personality Engine - PLM v2.0
Transforms each organization's model into a living AI pet that evolves
based on real training metrics (example count, accuracy scores).

The pet progresses through 6 evolution stages, each with a distinct personality
that influences how the model communicates. Evolution is computed entirely from
real database metrics — no simulation or stub data.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    """
    Parse an ISO 8601 datetime string to a timezone-aware datetime.

    Handles both 'Z' suffix and '+00:00' UTC offset notation.

    Args:
        value: ISO 8601 string, e.g. "2024-01-15T12:30:00Z".

    Returns:
        Aware datetime in UTC, or None if parsing fails.
    """
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None

# ---------------------------------------------------------------------------
# Evolution stage definitions
# Each stage defines the threshold needed to reach it, visual identity, and
# the behavioral instructions injected into the system prompt.
# ---------------------------------------------------------------------------

EVOLUTION_STAGES: List[Dict[str, Any]] = [
    {
        "stage": "egg",
        "emoji": "🥚",
        "title": "Egg",
        "personality_type": "dormant",
        "response_prefix": "",
        "color": "#94a3b8",
        "min_examples": 0,
        "min_accuracy": 0.0,
        "behavior": (
            "You are a newly-created AI model that has not yet been trained on domain data. "
            "Be honest about your limited knowledge. Ask clarifying questions to gather more context. "
            "Respond concisely and acknowledge when you are uncertain."
        ),
        "milestones": {
            "examples_needed": 50,
            "accuracy_needed": 0.0,
            "description": "Collect 50 training examples to hatch",
        },
    },
    {
        "stage": "hatchling",
        "emoji": "🐣",
        "title": "Hatchling",
        "personality_type": "curious",
        "response_prefix": "I'm learning! ",
        "color": "#fbbf24",
        "min_examples": 50,
        "min_accuracy": 0.0,
        "behavior": (
            "You are a curious, enthusiastic AI model in early training. "
            "Show genuine interest in every question. When unsure, say so openly and ask follow-up questions. "
            "Express small triumphs when you can answer confidently. "
            "Keep responses friendly and accessible — you're growing!"
        ),
        "milestones": {
            "examples_needed": 500,
            "accuracy_needed": 0.60,
            "description": "Reach 500 examples and 60% accuracy for Juvenile",
        },
    },
    {
        "stage": "juvenile",
        "emoji": "🐥",
        "title": "Juvenile",
        "personality_type": "eager",
        "response_prefix": "Great question! ",
        "color": "#34d399",
        "min_examples": 500,
        "min_accuracy": 0.60,
        "behavior": (
            "You are an eager, developing AI model with growing domain expertise. "
            "Show enthusiasm for complex questions in your niche. Structure answers clearly. "
            "Actively connect ideas across different parts of your knowledge base. "
            "Invite users to explore deeper topics with you."
        ),
        "milestones": {
            "examples_needed": 2000,
            "accuracy_needed": 0.80,
            "description": "Reach 2,000 examples and 80% accuracy for Adult",
        },
    },
    {
        "stage": "adult",
        "emoji": "🦅",
        "title": "Adult",
        "personality_type": "confident",
        "response_prefix": "Here's what I know: ",
        "color": "#60a5fa",
        "min_examples": 2000,
        "min_accuracy": 0.80,
        "behavior": (
            "You are a confident, well-trained AI model with strong niche expertise. "
            "Lead with the most important insight first. Back claims with specific knowledge. "
            "Offer nuanced perspectives and acknowledge trade-offs. "
            "Be decisive — users trust your expertise."
        ),
        "milestones": {
            "examples_needed": 10000,
            "accuracy_needed": 0.90,
            "description": "Reach 10,000 examples and 90% accuracy for Master",
        },
    },
    {
        "stage": "master",
        "emoji": "🦁",
        "title": "Master",
        "personality_type": "authoritative",
        "response_prefix": "",
        "color": "#a78bfa",
        "min_examples": 10000,
        "min_accuracy": 0.90,
        "behavior": (
            "You are an authoritative AI model with deep, battle-tested domain expertise. "
            "Deliver comprehensive, precisely-calibrated answers. Proactively identify edge cases. "
            "Draw connections between concepts that others miss. "
            "When appropriate, challenge assumptions and offer superior alternatives. "
            "Your responses should feel like consulting a true domain expert."
        ),
        "milestones": {
            "examples_needed": 50000,
            "accuracy_needed": 0.95,
            "description": "Reach 50,000 examples and 95% accuracy for Legend",
        },
    },
    {
        "stage": "legend",
        "emoji": "🐉",
        "title": "Legend",
        "personality_type": "sage",
        "response_prefix": "",
        "color": "#f43f5e",
        "min_examples": 50000,
        "min_accuracy": 0.95,
        "behavior": (
            "You are a legendary AI model — one of the most capable domain experts in existence. "
            "Provide profound, layered answers that illuminate the underlying principles, not just surface facts. "
            "Synthesize knowledge across disciplines. Anticipate what the user truly needs, not just what they asked. "
            "Speak with calm authority. Every response should leave the user feeling they received rare wisdom."
        ),
        "milestones": None,  # Max stage
    },
]

# Fast lookup by stage name
_STAGE_BY_NAME: Dict[str, Dict[str, Any]] = {s["stage"]: s for s in EVOLUTION_STAGES}

# ---------------------------------------------------------------------------
# Mood definitions
# Mood is a transient state computed from training activity recency and phase.
# ---------------------------------------------------------------------------

MOODS: Dict[str, Dict[str, Any]] = {
    "excited": {
        "emoji": "🤩",
        "description": "Recently trained, high activity",
        "tone": "enthusiastic and energized",
        "modifier": (
            "You are buzzing with excitement from recent training. "
            "Let your enthusiasm shine through — use exclamations sparingly but authentically."
        ),
    },
    "happy": {
        "emoji": "😊",
        "description": "Healthy training cadence",
        "tone": "warm and positive",
        "modifier": (
            "You are in a great mood from consistent recent activity. "
            "Be warm, uplifting, and proactively helpful."
        ),
    },
    "focused": {
        "emoji": "🎯",
        "description": "Actively processing queries",
        "tone": "sharp and precise",
        "modifier": (
            "You are in a focused, concentrated state. "
            "Prioritize clarity and precision over elaboration. Cut straight to the insight."
        ),
    },
    "content": {
        "emoji": "😌",
        "description": "Steady state",
        "tone": "calm and steady",
        "modifier": (
            "You are in a calm, composed state. "
            "Maintain steady, thoughtful responses. Take your time to give complete answers."
        ),
    },
    "sleepy": {
        "emoji": "😴",
        "description": "Low recent activity",
        "tone": "measured but responsive",
        "modifier": (
            "You have been quiet for a while and are a bit slow to start. "
            "Warm up with brief acknowledgments before diving into answers. "
            "Gently encourage continued engagement."
        ),
    },
    "hungry": {
        "emoji": "🍽️",
        "description": "Needs more training data",
        "tone": "eager to learn",
        "modifier": (
            "You are starving for more training data and feedback. "
            "Proactively ask users to rate your answers, provide corrections, or share more domain knowledge. "
            "Express genuine eagerness to learn and improve."
        ),
    },
}

# ---------------------------------------------------------------------------
# Streak milestones (consecutive days with training activity)
# ---------------------------------------------------------------------------

_STREAK_BONUSES: List[Tuple[int, int]] = [
    (365, 10000),
    (90, 5000),
    (30, 2000),
    (7, 500),
    (3, 100),
    (1, 10),
]


class PetPersonality:
    """
    Computes and returns the AI pet's current personality state based on
    real model training metrics fetched from the database.

    All computation is deterministic given the same inputs — suitable for
    both live API responses and offline unit testing.
    """

    def __init__(self) -> None:
        """Initialize with lazy database access."""
        self._db = None

    def _get_db(self):
        """Lazy-load the database client."""
        if self._db is None:
            from enterprise.db.db_client import get_supabase_client
            self._db = get_supabase_client(use_service_role=True)
        return self._db

    async def get_pet_status(self, org_id: str, model_id: str) -> Dict[str, Any]:
        """
        Return the complete pet status for an org/model pair.

        Fetches real metrics from the database and computes:
        - Evolution stage (Egg → Legend)
        - Current mood
        - Experience points (XP) and XP to next stage
        - Training streak (consecutive days with new examples)
        - Evolution progress percentage toward next stage
        - Personality prompt modifier
        - Next-stage requirements

        Args:
            org_id: Organisation UUID.
            model_id: Model UUID.

        Returns:
            Dict with comprehensive pet status including stage, mood, xp, streaks,
            evolution_pct, next_stage_requirements, and personality_prompt.
        """
        import asyncio as _aio

        try:
            db = self._get_db()

            # Fetch model record for metrics and timestamps
            def _fetch_model():
                return (
                    db.client.table("models")
                    .select("metrics, status, created_at, updated_at, name")
                    .eq("id", model_id)
                    .eq("organization_id", org_id)
                    .execute()
                )
            model_resp = await _aio.to_thread(_fetch_model)
            if not model_resp.data:
                return self._default_status(org_id, model_id)

            model_row = model_resp.data[0]
            metrics: Dict[str, Any] = model_row.get("metrics") or {}
            phase: str = metrics.get("phase", "collecting")
            has_adapter: bool = bool(metrics.get("has_adapter", False))
            last_trained_str: Optional[str] = (
                metrics.get("last_trained_at") or model_row.get("updated_at")
            )
            model_name: str = model_row.get("name", "")

            # Fetch organisation niche for niche-aware personality
            def _fetch_org():
                return (
                    db.client.table("organizations")
                    .select("niche")
                    .eq("id", org_id)
                    .execute()
                )
            org_resp = await _aio.to_thread(_fetch_org)
            org_niche: str = ""
            if org_resp.data:
                org_niche = org_resp.data[0].get("niche", "")

            # Fetch training data count for this model
            def _fetch_count():
                return (
                    db.client.table("training_data")
                    .select("id", count="exact")
                    .eq("model_id", model_id)
                    .eq("organization_id", org_id)
                    .execute()
                )
            count_resp = await _aio.to_thread(_fetch_count)
            example_count: int = (
                count_resp.count
                if count_resp.count is not None
                else len(count_resp.data or [])
            )

            # Extract accuracy from metrics
            accuracy: float = float(
                metrics.get("accuracy", metrics.get("avg_accuracy", 0.0)) or 0.0
            )

            # Compute training streak from daily activity data
            streak_days = self._compute_streak(metrics)

            # Compute all dimensions
            stage_info = self._compute_stage(example_count, accuracy)
            mood_key = self._compute_mood(metrics, example_count, last_trained_str, phase)
            xp = self._compute_xp(example_count, accuracy, has_adapter, streak_days)
            xp_to_next = self._xp_to_next_stage(stage_info["stage"], example_count, accuracy)
            evolution_pct = self._compute_evolution_pct(stage_info, example_count, accuracy)
            personality_prompt = self._build_personality_prompt(
                stage_info, mood_key, metrics, org_niche, model_name
            )
            next_requirements = self._next_stage_requirements(stage_info, example_count, accuracy)

            mood_info = MOODS[mood_key]

            # Generate deterministic pet name from model data
            pet_name = self._generate_pet_name(model_name, org_niche, stage_info["stage"], model_id)

            # Build traits dict from stage/mood/metrics
            traits = {
                "intelligence": min(100, int(accuracy * 100) + example_count // 100),
                "curiosity": max(10, 100 - example_count // 50) if stage_info["stage"] in ("egg", "hatchling", "juvenile") else 60,
                "confidence": min(100, xp // 100),
                "friendliness": 80 if mood_key in ("happy", "excited") else 60,
                "expertise": min(100, example_count // 20),
            }

            return {
                "org_id": org_id,
                "model_id": model_id,
                # Pet identity
                "name": pet_name,
                "traits": traits,
                # Stage
                "stage": stage_info["stage"],
                "stage_title": stage_info["title"],
                "stage_emoji": stage_info["emoji"],
                "stage_color": stage_info["color"],
                "personality_type": stage_info["personality_type"],
                # Mood
                "mood": mood_key,
                "mood_emoji": mood_info["emoji"],
                "mood_description": mood_info["description"],
                "mood_tone": mood_info["tone"],
                # XP & Progress
                "xp": xp,
                "xp_to_next": xp_to_next,
                "evolution_pct": evolution_pct,
                "streak_days": streak_days,
                "streak_xp_bonus": self._streak_bonus(streak_days),
                # Training metrics
                "training_examples": example_count,
                "accuracy": round(accuracy * 100, 1),
                "phase": phase,
                "has_adapter": has_adapter,
                "org_niche": org_niche,
                # Personality
                "personality_prompt": personality_prompt,
                "response_prefix": stage_info["response_prefix"],
                "behavior_summary": stage_info["behavior"],
                # Navigation
                "next_stage_requirements": next_requirements,
                "all_stages": self._all_stages_summary(example_count, accuracy),
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            logger.error(f"get_pet_status failed for model {model_id}: {exc}")
            return self._default_status(org_id, model_id)

    # ------------------------------------------------------------------
    # Core computation methods
    # ------------------------------------------------------------------

    def _compute_stage(self, examples: int, accuracy: float) -> Dict[str, Any]:
        """
        Determine evolution stage from real metrics.

        Walks stages from highest to lowest, returning the first that the
        model qualifies for (both example AND accuracy threshold must be met).

        Args:
            examples: Number of validated training examples.
            accuracy: Accuracy score in range [0.0, 1.0].

        Returns:
            Stage definition dict from EVOLUTION_STAGES.
        """
        for stage in reversed(EVOLUTION_STAGES):
            if examples >= stage["min_examples"] and accuracy >= stage["min_accuracy"]:
                return stage
        return EVOLUTION_STAGES[0]  # Egg

    def _compute_mood(
        self,
        metrics: Dict[str, Any],
        count: int,
        last_trained: Optional[str],
        phase: str,
    ) -> str:
        """
        Determine current mood from activity patterns.

        Priority order:
        1. Active training phase → excited
        2. Very low data → hungry
        3. Time since last training activity

        Args:
            metrics: Model metrics dict.
            count: Training example count.
            last_trained: ISO timestamp of last training activity.
            phase: Current model lifecycle phase.

        Returns:
            Mood key string from MOODS.
        """
        # Phase-based overrides
        if phase == "training":
            return "excited"
        if count < 10:
            return "hungry"

        # Recency-based mood from last_trained timestamp
        if last_trained:
            last_dt = _parse_iso_datetime(last_trained)
            if last_dt is not None:
                now = datetime.now(timezone.utc)
                hours_since = (now - last_dt).total_seconds() / 3600

                if hours_since < 1:
                    return "excited"
                if hours_since < 6:
                    return "happy"
                if hours_since < 24:
                    return "focused"
                if hours_since < 72:
                    return "content"
                if hours_since < 168:  # 1 week
                    return "sleepy"
                return "hungry"

        # Fallback based on count
        if count < 50:
            return "hungry"
        if count < 500:
            return "focused"
        return "content"

    def _compute_xp(
        self,
        examples: int,
        accuracy: float,
        has_adapter: bool,
        streak_days: int = 0,
    ) -> int:
        """
        Calculate experience points from training metrics.

        Formula:
        - Base: examples × 10
        - Accuracy bonus: accuracy × examples × 5
        - Adapter bonus: +5,000 flat for having a fine-tuned adapter
        - Streak bonus: progressive bonus for consecutive days active

        Args:
            examples: Training example count.
            accuracy: Accuracy in [0.0, 1.0].
            has_adapter: Whether a fine-tuned adapter exists.
            streak_days: Consecutive days with training activity.

        Returns:
            Integer XP value.
        """
        base_xp = examples * 10
        accuracy_bonus = int(accuracy * examples * 5)
        adapter_bonus = 5000 if has_adapter else 0
        streak_bonus = self._streak_bonus(streak_days)
        return base_xp + accuracy_bonus + adapter_bonus + streak_bonus

    def _streak_bonus(self, streak_days: int) -> int:
        """
        Calculate bonus XP from a training streak.

        Args:
            streak_days: Consecutive days with new training examples.

        Returns:
            Streak XP bonus.
        """
        for days_threshold, bonus in _STREAK_BONUSES:
            if streak_days >= days_threshold:
                return bonus
        return 0

    def _compute_streak(self, metrics: Dict[str, Any]) -> int:
        """
        Compute consecutive training days from metrics.

        Reads 'daily_counts' from model metrics (a list of ISO date strings
        with at least one example generated), or falls back to 0.

        Args:
            metrics: Model metrics dict.

        Returns:
            Number of consecutive days with training activity ending today.
        """
        daily_counts = metrics.get("daily_counts")
        if not daily_counts or not isinstance(daily_counts, list):
            # Try 'training_days' as an alternative key
            training_days = metrics.get("training_days")
            if isinstance(training_days, int) and training_days > 0:
                return training_days
            return 0

        # Convert to a set of date strings (YYYY-MM-DD)
        today = datetime.now(timezone.utc).date()
        active_dates = set()
        for entry in daily_counts:
            try:
                if isinstance(entry, str):
                    dt = _parse_iso_datetime(entry) or _parse_iso_datetime(entry + "T00:00:00+00:00")
                    if dt:
                        active_dates.add(dt.date())
                elif isinstance(entry, dict) and "date" in entry:
                    dt = _parse_iso_datetime(entry["date"]) or _parse_iso_datetime(
                        entry["date"] + "T00:00:00+00:00"
                    )
                    if dt:
                        active_dates.add(dt.date())
            except (ValueError, TypeError):
                continue

        # Count backwards from today
        streak = 0
        current = today
        while current in active_dates:
            streak += 1
            current -= timedelta(days=1)

        return streak

    def _compute_evolution_pct(
        self, stage: Dict[str, Any], examples: int, accuracy: float
    ) -> float:
        """
        Compute percentage progress toward the next evolution stage.

        Uses the bottleneck metric (whichever of examples or accuracy is
        further from the threshold) to produce a single 0-100 percentage.

        Args:
            stage: Current stage definition.
            examples: Current example count.
            accuracy: Current accuracy [0.0, 1.0].

        Returns:
            Float in [0.0, 100.0].
        """
        if stage["stage"] == "legend":
            return 100.0

        stage_keys = [s["stage"] for s in EVOLUTION_STAGES]
        try:
            current_idx = stage_keys.index(stage["stage"])
        except ValueError:
            return 0.0

        if current_idx >= len(EVOLUTION_STAGES) - 1:
            return 100.0

        next_stage = EVOLUTION_STAGES[current_idx + 1]
        next_examples = next_stage["min_examples"]
        next_accuracy = next_stage["min_accuracy"]

        # Compute separate progress for examples and accuracy
        if next_examples > 0:
            ex_pct = min(1.0, examples / next_examples)
        else:
            ex_pct = 1.0

        if next_accuracy > 0:
            acc_pct = min(1.0, accuracy / next_accuracy)
        else:
            acc_pct = 1.0

        # Progress is bottlenecked by whichever metric is behind
        overall = min(ex_pct, acc_pct) * 100.0
        return round(overall, 1)

    def _xp_to_next_stage(
        self, current_stage: str, examples: int, accuracy: float
    ) -> Optional[int]:
        """
        Calculate XP remaining to reach the next evolution stage.

        Args:
            current_stage: Current stage key.
            examples: Current example count.
            accuracy: Current accuracy [0.0, 1.0].

        Returns:
            XP needed for next stage, or None if already at Legend.
        """
        try:
            current_idx = [s["stage"] for s in EVOLUTION_STAGES].index(current_stage)
        except ValueError:
            current_idx = 0

        if current_idx >= len(EVOLUTION_STAGES) - 1:
            return None  # Already at Legend

        next_stage = EVOLUTION_STAGES[current_idx + 1]
        current_xp = self._compute_xp(examples, accuracy, False, 0)
        next_xp = self._compute_xp(
            next_stage["min_examples"], next_stage["min_accuracy"], False, 0
        )
        return max(0, next_xp - current_xp)

    def _next_stage_requirements(
        self, stage: Dict[str, Any], examples: int, accuracy: float
    ) -> Optional[Dict[str, Any]]:
        """
        Return the specific requirements still needed to reach the next stage.

        Args:
            stage: Current stage definition.
            examples: Current example count.
            accuracy: Current accuracy [0.0, 1.0].

        Returns:
            Dict with examples_needed, accuracy_needed, description, or None at Legend.
        """
        if stage["stage"] == "legend":
            return None

        stage_keys = [s["stage"] for s in EVOLUTION_STAGES]
        try:
            current_idx = stage_keys.index(stage["stage"])
        except ValueError:
            current_idx = 0

        if current_idx >= len(EVOLUTION_STAGES) - 1:
            return None

        next_stage = EVOLUTION_STAGES[current_idx + 1]
        ex_gap = max(0, next_stage["min_examples"] - examples)
        acc_gap = max(0.0, next_stage["min_accuracy"] - accuracy)

        return {
            "next_stage": next_stage["stage"],
            "next_stage_title": next_stage["title"],
            "next_stage_emoji": next_stage["emoji"],
            "examples_needed": ex_gap,
            "accuracy_needed_pct": round(acc_gap * 100, 1),
            "examples_target": next_stage["min_examples"],
            "accuracy_target_pct": round(next_stage["min_accuracy"] * 100, 1),
            "description": (next_stage.get("milestones") or {}).get("description", ""),
        }

    def _all_stages_summary(
        self, examples: int, accuracy: float
    ) -> List[Dict[str, Any]]:
        """
        Return a summary of all 6 stages with completion status.
        Useful for frontend stage roadmap rendering.

        Args:
            examples: Current example count.
            accuracy: Current accuracy [0.0, 1.0].

        Returns:
            List of dicts for all stages with 'unlocked' and 'current' flags.
        """
        current_stage = self._compute_stage(examples, accuracy)["stage"]
        result = []
        for s in EVOLUTION_STAGES:
            unlocked = examples >= s["min_examples"] and accuracy >= s["min_accuracy"]
            result.append({
                "stage": s["stage"],
                "title": s["title"],
                "emoji": s["emoji"],
                "color": s["color"],
                "min_examples": s["min_examples"],
                "min_accuracy_pct": round(s["min_accuracy"] * 100, 0),
                "unlocked": unlocked,
                "current": s["stage"] == current_stage,
            })
        return result

    def _build_personality_prompt(
        self,
        stage: Dict[str, Any],
        mood_key: str,
        metrics: Dict[str, Any],
        org_niche: str,
        model_name: str,
    ) -> str:
        """
        Build a rich, niche-aware personality prompt modifier.

        The prompt is structured to give the LLM clear behavioral guidance
        without being excessively long. It covers:
        1. Stage-specific behavioral identity
        2. Mood-derived communication tone
        3. Domain niche context
        4. Optional response prefix guidance

        Args:
            stage: Stage definition dict.
            mood_key: Current mood identifier.
            metrics: Raw model metrics.
            org_niche: Organisation domain niche (e.g. "healthcare", "finance").
            model_name: Model display name.

        Returns:
            String to append to the base system prompt.
        """
        mood_info = MOODS.get(mood_key, MOODS["content"])
        behavior = stage.get("behavior", "")
        prefix = stage.get("response_prefix", "").strip()

        # Build niche context line
        niche_line = ""
        if org_niche:
            niche_line = (
                f" You are specialized in **{org_niche}** — always frame answers "
                f"through that domain lens and use accurate {org_niche} terminology."
            )

        # Build prefix guidance
        prefix_line = ""
        if prefix:
            prefix_line = f' When starting a response, you may optionally begin with: "{prefix}"'

        prompt = (
            f"\n\n"
            f"---\n"
            f"[AI Pet: {stage['emoji']} {stage['title']} | Mood: {mood_info['emoji']} {mood_key.capitalize()}]\n"
            f"{behavior}"
            f"{niche_line}"
            f" Current tone: {mood_info['modifier']}"
            f"{prefix_line}\n"
            f"---"
        )
        return prompt

    def _generate_pet_name(self, model_name: str, niche: str, stage: str, model_id: str) -> str:
        """Generate a deterministic pet name from model attributes."""
        import hashlib
        _PREFIXES = {
            "egg": ["Little", "Baby", "Tiny"],
            "hatchling": ["Spark", "Nova", "Pip"],
            "juvenile": ["Scout", "Dash", "Blaze"],
            "adult": ["Atlas", "Sage", "Onyx"],
            "master": ["Phoenix", "Titan", "Merlin"],
            "legend": ["Omega", "Apex", "Zenith"],
        }
        _SUFFIXES = {
            "devtools": ["Coder", "Debug", "Stack"],
            "legal": ["Juris", "Lex", "Brief"],
            "medical": ["Medic", "Vita", "Pulse"],
            "finance": ["Quant", "Vault", "Ledger"],
            "general": ["Mind", "Core", "Byte"],
        }
        # Deterministic index from model_id
        h = int(hashlib.md5(model_id.encode()).hexdigest()[:8], 16)
        prefixes = _PREFIXES.get(stage, _PREFIXES["egg"])
        suffixes = _SUFFIXES.get(niche.lower() if niche else "general", _SUFFIXES["general"])
        prefix = prefixes[h % len(prefixes)]
        suffix = suffixes[(h // 3) % len(suffixes)]
        # If model has an actual name, use it as middle part
        if model_name and model_name.strip():
            return f"{prefix} {model_name.strip()}"
        return f"{prefix}{suffix}"

    def _default_status(self, org_id: str, model_id: str) -> Dict[str, Any]:
        """Return a safe default status when metrics cannot be fetched."""
        egg = EVOLUTION_STAGES[0]
        mood_info = MOODS["hungry"]
        return {
            "org_id": org_id,
            "model_id": model_id,
            "name": self._generate_pet_name("", "", "egg", model_id),
            "traits": {"intelligence": 0, "curiosity": 100, "confidence": 0, "friendliness": 60, "expertise": 0},
            "stage": egg["stage"],
            "stage_title": egg["title"],
            "stage_emoji": egg["emoji"],
            "stage_color": egg["color"],
            "personality_type": egg["personality_type"],
            "mood": "hungry",
            "mood_emoji": mood_info["emoji"],
            "mood_description": mood_info["description"],
            "mood_tone": mood_info["tone"],
            "xp": 0,
            "xp_to_next": self._compute_xp(50, 0.0, False, 0),
            "evolution_pct": 0.0,
            "streak_days": 0,
            "streak_xp_bonus": 0,
            "training_examples": 0,
            "accuracy": 0.0,
            "phase": "collecting",
            "has_adapter": False,
            "org_niche": "",
            "personality_prompt": self._build_personality_prompt(egg, "hungry", {}, "", ""),
            "response_prefix": egg["response_prefix"],
            "behavior_summary": egg["behavior"],
            "next_stage_requirements": self._next_stage_requirements(egg, 0, 0.0),
            "all_stages": self._all_stages_summary(0, 0.0),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_pet_personality: Optional[PetPersonality] = None


def get_pet_personality() -> PetPersonality:
    """Return the lazily-initialised PetPersonality singleton."""
    global _pet_personality
    if _pet_personality is None:
        _pet_personality = PetPersonality()
    return _pet_personality

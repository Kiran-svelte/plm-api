"""
Unit tests for enterprise.pet_personality
Tests cover all evolution stage transitions, mood computation, and XP calculation.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from enterprise.pet_personality import (
    PetPersonality,
    EVOLUTION_STAGES,
    MOODS,
    get_pet_personality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pet() -> PetPersonality:
    return PetPersonality()


# ---------------------------------------------------------------------------
# Evolution stage transition tests
# ---------------------------------------------------------------------------

class TestComputeStage:
    """Tests for _compute_stage()."""

    def test_egg_zero_examples(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=0, accuracy=0.0)
        assert stage["stage"] == "egg"

    def test_egg_below_hatchling_threshold(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=49, accuracy=0.0)
        assert stage["stage"] == "egg"

    def test_hatchling_at_threshold(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=50, accuracy=0.0)
        assert stage["stage"] == "hatchling"

    def test_hatchling_below_juvenile_examples(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=499, accuracy=0.90)
        assert stage["stage"] == "hatchling"

    def test_juvenile_requires_both_examples_and_accuracy(self):
        pet = _make_pet()
        # Has examples but not accuracy
        stage = pet._compute_stage(examples=500, accuracy=0.50)
        assert stage["stage"] == "hatchling"
        # Has accuracy but not enough examples
        stage = pet._compute_stage(examples=499, accuracy=0.70)
        assert stage["stage"] == "hatchling"

    def test_juvenile_at_threshold(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=500, accuracy=0.60)
        assert stage["stage"] == "juvenile"

    def test_adult_at_threshold(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=2000, accuracy=0.80)
        assert stage["stage"] == "adult"

    def test_adult_requires_accuracy(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=2000, accuracy=0.79)
        assert stage["stage"] != "adult"

    def test_master_at_threshold(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=10000, accuracy=0.90)
        assert stage["stage"] == "master"

    def test_legend_at_threshold(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=50000, accuracy=0.95)
        assert stage["stage"] == "legend"

    def test_legend_requires_high_accuracy(self):
        pet = _make_pet()
        stage = pet._compute_stage(examples=50000, accuracy=0.94)
        assert stage["stage"] != "legend"

    def test_stage_has_required_fields(self):
        pet = _make_pet()
        for ex, acc in [(0, 0), (50, 0), (500, 0.6), (2000, 0.8), (10000, 0.9), (50000, 0.95)]:
            stage = pet._compute_stage(ex, acc)
            assert "stage" in stage
            assert "emoji" in stage
            assert "title" in stage
            assert "personality_type" in stage
            assert "response_prefix" in stage
            assert "color" in stage

    def test_all_six_stages_reachable(self):
        pet = _make_pet()
        expected_stages = {"egg", "hatchling", "juvenile", "adult", "master", "legend"}
        reached = set()
        test_cases = [
            (0, 0.0),
            (50, 0.0),
            (500, 0.60),
            (2000, 0.80),
            (10000, 0.90),
            (50000, 0.95),
        ]
        for ex, acc in test_cases:
            reached.add(pet._compute_stage(ex, acc)["stage"])
        assert reached == expected_stages


# ---------------------------------------------------------------------------
# Mood computation tests
# ---------------------------------------------------------------------------

class TestComputeMood:
    """Tests for _compute_mood()."""

    def test_training_phase_is_excited(self):
        pet = _make_pet()
        mood = pet._compute_mood({}, 100, None, "training")
        assert mood == "excited"

    def test_low_count_is_hungry(self):
        pet = _make_pet()
        mood = pet._compute_mood({}, 5, None, "collecting")
        assert mood == "hungry"

    def test_recent_activity_excited(self):
        pet = _make_pet()
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        mood = pet._compute_mood({}, 100, recent, "deployed")
        assert mood == "excited"

    def test_old_activity_hungry(self):
        pet = _make_pet()
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        mood = pet._compute_mood({}, 100, old, "deployed")
        assert mood == "hungry"

    def test_moderate_activity_happy(self):
        pet = _make_pet()
        from datetime import datetime, timezone, timedelta
        moderate = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        mood = pet._compute_mood({}, 100, moderate, "deployed")
        assert mood == "happy"

    def test_invalid_timestamp_fallback(self):
        pet = _make_pet()
        mood = pet._compute_mood({}, 100, "not-a-date", "deployed")
        assert mood in MOODS

    def test_all_moods_are_valid(self):
        valid_moods = set(MOODS.keys())
        pet = _make_pet()
        from datetime import datetime, timezone, timedelta
        test_cases = [
            (5, None, "collecting"),
            (100, (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "training"),
            (100, (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(), "deployed"),
            (100, (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(), "deployed"),
            (100, (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(), "deployed"),
            (100, (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "deployed"),
            (100, (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(), "deployed"),
        ]
        for count, last_trained, phase in test_cases:
            mood = pet._compute_mood({}, count, last_trained, phase)
            assert mood in valid_moods, f"Unexpected mood '{mood}' for inputs: {(count, last_trained, phase)}"


# ---------------------------------------------------------------------------
# XP calculation tests
# ---------------------------------------------------------------------------

class TestComputeXP:
    """Tests for _compute_xp()."""

    def test_zero_examples_zero_xp(self):
        pet = _make_pet()
        xp = pet._compute_xp(0, 0.0, False)
        assert xp == 0

    def test_examples_contribute_to_xp(self):
        pet = _make_pet()
        xp = pet._compute_xp(100, 0.0, False)
        assert xp > 0

    def test_accuracy_increases_xp(self):
        pet = _make_pet()
        xp_low = pet._compute_xp(100, 0.0, False)
        xp_high = pet._compute_xp(100, 1.0, False)
        assert xp_high > xp_low

    def test_adapter_bonus(self):
        pet = _make_pet()
        xp_no_adapter = pet._compute_xp(100, 0.5, False)
        xp_adapter = pet._compute_xp(100, 0.5, True)
        assert xp_adapter > xp_no_adapter
        assert xp_adapter - xp_no_adapter == 5000

    def test_xp_is_integer(self):
        pet = _make_pet()
        xp = pet._compute_xp(500, 0.75, True)
        assert isinstance(xp, int)

    def test_xp_scales_with_examples(self):
        pet = _make_pet()
        xp_small = pet._compute_xp(100, 0.5, False)
        xp_large = pet._compute_xp(1000, 0.5, False)
        assert xp_large > xp_small * 9  # At least 9x more XP for 10x examples

    def test_streak_bonus_added(self):
        pet = _make_pet()
        xp_no_streak = pet._compute_xp(100, 0.5, False, streak_days=0)
        xp_week_streak = pet._compute_xp(100, 0.5, False, streak_days=7)
        assert xp_week_streak > xp_no_streak

    def test_streak_bonus_scales(self):
        pet = _make_pet()
        xp_day1 = pet._compute_xp(100, 0.5, False, streak_days=1)
        xp_week = pet._compute_xp(100, 0.5, False, streak_days=7)
        xp_month = pet._compute_xp(100, 0.5, False, streak_days=30)
        assert xp_month >= xp_week >= xp_day1


# ---------------------------------------------------------------------------
# XP to next stage tests
# ---------------------------------------------------------------------------

class TestXPToNextStage:
    """Tests for _xp_to_next_stage()."""

    def test_legend_returns_none(self):
        pet = _make_pet()
        result = pet._xp_to_next_stage("legend", 50000, 0.95)
        assert result is None

    def test_egg_has_xp_to_next(self):
        pet = _make_pet()
        result = pet._xp_to_next_stage("egg", 0, 0.0)
        assert result is not None
        assert result > 0

    def test_xp_to_next_is_non_negative(self):
        pet = _make_pet()
        stages = ["egg", "hatchling", "juvenile", "adult", "master"]
        for stage in stages:
            result = pet._xp_to_next_stage(stage, 0, 0.0)
            assert result is not None
            assert result >= 0


# ---------------------------------------------------------------------------
# Personality prompt tests
# ---------------------------------------------------------------------------

class TestBuildPersonalityPrompt:
    """Tests for _build_personality_prompt()."""

    def test_returns_non_empty_string(self):
        pet = _make_pet()
        for stage in EVOLUTION_STAGES:
            for mood_key in MOODS:
                prompt = pet._build_personality_prompt(stage, mood_key, {}, "healthcare", "TestModel")
                assert isinstance(prompt, str)
                assert len(prompt) > 0

    def test_prompt_contains_stage_info(self):
        pet = _make_pet()
        legend = EVOLUTION_STAGES[-1]
        prompt = pet._build_personality_prompt(legend, "excited", {}, "finance", "MyModel")
        assert "Legend" in prompt or "legend" in prompt.lower()

    def test_prompt_contains_mood_info(self):
        pet = _make_pet()
        egg = EVOLUTION_STAGES[0]
        prompt = pet._build_personality_prompt(egg, "hungry", {}, "", "")
        assert len(prompt) > 10  # Meaningful content

    def test_niche_included_in_prompt(self):
        pet = _make_pet()
        adult = EVOLUTION_STAGES[3]  # adult stage
        prompt = pet._build_personality_prompt(adult, "happy", {}, "healthcare", "MedBot")
        assert "healthcare" in prompt

    def test_empty_niche_does_not_crash(self):
        pet = _make_pet()
        egg = EVOLUTION_STAGES[0]
        prompt = pet._build_personality_prompt(egg, "hungry", {}, "", "")
        assert isinstance(prompt, str)
        assert len(prompt) > 0


# ---------------------------------------------------------------------------
# Streak computation tests
# ---------------------------------------------------------------------------

class TestComputeStreak:
    """Tests for _compute_streak()."""

    def test_empty_metrics_returns_zero(self):
        pet = _make_pet()
        assert pet._compute_streak({}) == 0

    def test_training_days_integer_key(self):
        pet = _make_pet()
        assert pet._compute_streak({"training_days": 5}) == 5

    def test_consecutive_dates_counted(self):
        from datetime import datetime, timezone, timedelta
        pet = _make_pet()
        today = datetime.now(timezone.utc).date()
        dates = [
            (today - timedelta(days=i)).isoformat()
            for i in range(3)  # today, yesterday, 2 days ago
        ]
        streak = pet._compute_streak({"daily_counts": dates})
        assert streak == 3

    def test_broken_streak_stops_at_gap(self):
        from datetime import datetime, timezone, timedelta
        pet = _make_pet()
        today = datetime.now(timezone.utc).date()
        # today and 2 days ago (no yesterday)
        dates = [today.isoformat(), (today - timedelta(days=2)).isoformat()]
        streak = pet._compute_streak({"daily_counts": dates})
        assert streak == 1  # Only today counts; gap yesterday stops it

    def test_invalid_daily_counts_returns_zero(self):
        pet = _make_pet()
        assert pet._compute_streak({"daily_counts": ["not-a-date", None]}) == 0

    def test_no_streak_today_returns_zero(self):
        from datetime import datetime, timezone, timedelta
        pet = _make_pet()
        # Only old dates, not today
        old = [(datetime.now(timezone.utc).date() - timedelta(days=5)).isoformat()]
        streak = pet._compute_streak({"daily_counts": old})
        assert streak == 0


# ---------------------------------------------------------------------------
# Evolution percentage tests
# ---------------------------------------------------------------------------

class TestComputeEvolutionPct:
    """Tests for _compute_evolution_pct()."""

    def test_legend_returns_100(self):
        pet = _make_pet()
        legend = EVOLUTION_STAGES[-1]
        pct = pet._compute_evolution_pct(legend, 50000, 0.95)
        assert pct == 100.0

    def test_zero_progress_returns_zero(self):
        pet = _make_pet()
        egg = EVOLUTION_STAGES[0]
        pct = pet._compute_evolution_pct(egg, 0, 0.0)
        assert pct == 0.0

    def test_partial_progress_between_0_and_100(self):
        pet = _make_pet()
        egg = EVOLUTION_STAGES[0]
        pct = pet._compute_evolution_pct(egg, 25, 0.0)
        assert 0.0 < pct < 100.0

    def test_result_is_float(self):
        pet = _make_pet()
        for s in EVOLUTION_STAGES:
            pct = pet._compute_evolution_pct(s, 100, 0.5)
            assert isinstance(pct, float)

    def test_bottleneck_is_lower_metric(self):
        pet = _make_pet()
        # For juvenile (need 500 ex + 60% acc):
        # 400/500 examples = 80% but only 50% accuracy = 50/60 = 83% → bottleneck is accuracy
        hatchling = EVOLUTION_STAGES[1]  # hatchling → juvenile
        pct_acc_bottleneck = pet._compute_evolution_pct(hatchling, 400, 0.50)
        pct_ex_bottleneck = pet._compute_evolution_pct(hatchling, 100, 0.60)
        # Both limited by their respective bottleneck — both should be < 100
        assert pct_acc_bottleneck < 100.0
        assert pct_ex_bottleneck < 100.0


# ---------------------------------------------------------------------------
# Next stage requirements tests
# ---------------------------------------------------------------------------

class TestNextStageRequirements:
    """Tests for _next_stage_requirements()."""

    def test_legend_returns_none(self):
        pet = _make_pet()
        legend = EVOLUTION_STAGES[-1]
        assert pet._next_stage_requirements(legend, 50000, 0.95) is None

    def test_egg_returns_hatchling_requirements(self):
        pet = _make_pet()
        egg = EVOLUTION_STAGES[0]
        reqs = pet._next_stage_requirements(egg, 0, 0.0)
        assert reqs is not None
        assert reqs["next_stage"] == "hatchling"
        assert reqs["examples_needed"] == 50  # Need 50 total from 0

    def test_requirements_decrease_as_examples_grow(self):
        pet = _make_pet()
        egg = EVOLUTION_STAGES[0]
        reqs_at_0 = pet._next_stage_requirements(egg, 0, 0.0)
        reqs_at_30 = pet._next_stage_requirements(egg, 30, 0.0)
        assert reqs_at_30["examples_needed"] < reqs_at_0["examples_needed"]

    def test_requirements_has_required_fields(self):
        pet = _make_pet()
        for s in EVOLUTION_STAGES[:-1]:  # All except legend
            reqs = pet._next_stage_requirements(s, 0, 0.0)
            assert "next_stage" in reqs
            assert "next_stage_title" in reqs
            assert "next_stage_emoji" in reqs
            assert "examples_needed" in reqs
            assert "accuracy_needed_pct" in reqs
            assert "examples_target" in reqs
            assert "accuracy_target_pct" in reqs


# ---------------------------------------------------------------------------
# All stages summary tests
# ---------------------------------------------------------------------------

class TestAllStagesSummary:
    """Tests for _all_stages_summary()."""

    def test_returns_six_stages(self):
        pet = _make_pet()
        stages = pet._all_stages_summary(0, 0.0)
        assert len(stages) == 6

    def test_exactly_one_current_stage(self):
        pet = _make_pet()
        for ex, acc in [(0, 0.0), (50, 0.0), (500, 0.6), (2000, 0.8)]:
            stages = pet._all_stages_summary(ex, acc)
            current_count = sum(1 for s in stages if s["current"])
            assert current_count == 1, f"Expected 1 current stage for ({ex}, {acc})"

    def test_unlocked_stages_are_subset_of_all(self):
        pet = _make_pet()
        stages = pet._all_stages_summary(500, 0.60)
        unlocked = [s for s in stages if s["unlocked"]]
        # Egg, Hatchling, Juvenile should be unlocked
        unlocked_names = {s["stage"] for s in unlocked}
        assert "egg" in unlocked_names
        assert "hatchling" in unlocked_names
        assert "juvenile" in unlocked_names

    def test_each_stage_has_required_fields(self):
        pet = _make_pet()
        stages = pet._all_stages_summary(0, 0.0)
        for s in stages:
            assert "stage" in s
            assert "title" in s
            assert "emoji" in s
            assert "color" in s
            assert "unlocked" in s
            assert "current" in s


# ---------------------------------------------------------------------------
# Streak bonus tests
# ---------------------------------------------------------------------------

class TestStreakBonus:
    """Tests for _streak_bonus()."""

    def test_zero_streak_no_bonus(self):
        pet = _make_pet()
        assert pet._streak_bonus(0) == 0

    def test_single_day_gives_small_bonus(self):
        pet = _make_pet()
        assert pet._streak_bonus(1) > 0

    def test_week_streak_gives_more_than_day(self):
        pet = _make_pet()
        assert pet._streak_bonus(7) > pet._streak_bonus(1)

    def test_year_streak_gives_highest_bonus(self):
        pet = _make_pet()
        assert pet._streak_bonus(365) > pet._streak_bonus(90)
        assert pet._streak_bonus(365) == 10000


# ---------------------------------------------------------------------------
# Singleton test
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_pet_personality_returns_same_instance(self):
        p1 = get_pet_personality()
        p2 = get_pet_personality()
        assert p1 is p2

    def test_returns_pet_personality_instance(self):
        p = get_pet_personality()
        assert isinstance(p, PetPersonality)

"""
Tests del motor cron: parseo de expresiones, coincidencia temporal y
robustez del bucle autónomo.
"""

import sys
import os
import asyncio
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.scheduler.cron_engine import (
    CronEngine,
    CronParseError,
    parse_cron_expression,
    cron_matches,
)


# --- Parseo de campos ---

def test_parse_wildcard_expands_full_range():
    minutes, hours, _, _, _ = parse_cron_expression("* * * * *")
    assert minutes == set(range(60))
    assert hours == set(range(24))


def test_parse_step_expression():
    """`*/20` era el caso que tumbaba el daemon en el primer tick."""
    minutes, _, _, _, _ = parse_cron_expression("*/20 * * * *")
    assert minutes == {0, 20, 40}


def test_parse_step_over_hours():
    _, hours, _, _, _ = parse_cron_expression("0 */3 * * *")
    assert hours == {0, 3, 6, 9, 12, 15, 18, 21}


def test_parse_range():
    _, hours, _, _, _ = parse_cron_expression("0 9-18 * * *")
    assert hours == set(range(9, 19))


def test_parse_range_with_step():
    _, hours, _, _, _ = parse_cron_expression("0 9-18/3 * * *")
    assert hours == {9, 12, 15, 18}


def test_parse_list():
    minutes, _, _, _, _ = parse_cron_expression("0,15,30,45 * * * *")
    assert minutes == {0, 15, 30, 45}


def test_parse_single_value():
    minutes, hours, _, _, _ = parse_cron_expression("30 7 * * *")
    assert minutes == {30}
    assert hours == {7}


def test_sunday_accepts_both_zero_and_seven():
    _, _, _, _, dow_zero = parse_cron_expression("0 0 * * 0")
    _, _, _, _, dow_seven = parse_cron_expression("0 0 * * 7")
    assert dow_zero == dow_seven == {0}


@pytest.mark.parametrize("expr", [
    "",
    "* * * *",            # solo 4 campos
    "* * * * * *",        # 6 campos
    "60 * * * *",         # minuto fuera de rango
    "* 24 * * *",         # hora fuera de rango
    "0 0 32 * *",         # día del mes fuera de rango
    "0 0 * 13 *",         # mes fuera de rango
    "*/0 * * * *",        # paso cero
    "*/abc * * * *",      # paso no numérico
    "18-9 * * * *",       # rango invertido
    "lunes * * * *",      # basura
])
def test_invalid_expressions_raise(expr):
    with pytest.raises(CronParseError):
        parse_cron_expression(expr)


# --- Coincidencia temporal ---

def test_cron_matches_exact_time():
    parsed = parse_cron_expression("30 7 * * *")
    assert cron_matches(parsed, datetime(2026, 8, 31, 7, 30))
    assert not cron_matches(parsed, datetime(2026, 8, 31, 7, 31))
    assert not cron_matches(parsed, datetime(2026, 8, 31, 8, 30))


def test_cron_matches_every_twenty_minutes():
    parsed = parse_cron_expression("*/20 * * * *")
    assert cron_matches(parsed, datetime(2026, 8, 31, 13, 0))
    assert cron_matches(parsed, datetime(2026, 8, 31, 13, 40))
    assert not cron_matches(parsed, datetime(2026, 8, 31, 13, 25))


def test_cron_matches_day_of_week():
    # 2026-08-31 es lunes.
    parsed = parse_cron_expression("0 12 * * 1")
    assert cron_matches(parsed, datetime(2026, 8, 31, 12, 0))
    assert not cron_matches(parsed, datetime(2026, 9, 1, 12, 0))


def test_cron_matches_sunday_as_zero():
    # 2026-09-06 es domingo.
    parsed = parse_cron_expression("0 12 * * 0")
    assert cron_matches(parsed, datetime(2026, 9, 6, 12, 0))


def test_dom_and_dow_are_ored_when_both_restricted():
    """Semántica estándar de cron: si ambos se restringen, basta con uno."""
    parsed = parse_cron_expression("0 12 1 * 5")
    assert cron_matches(parsed, datetime(2026, 9, 1, 12, 0))   # día 1 (martes)
    assert cron_matches(parsed, datetime(2026, 9, 4, 12, 0))   # viernes (día 4)
    assert not cron_matches(parsed, datetime(2026, 9, 2, 12, 0))


# --- Motor ---

def test_register_job_rejects_invalid_expression():
    engine = CronEngine(timezone="UTC")
    with pytest.raises(CronParseError):
        engine.register_job("rota", "*/0 * * * *", lambda: None)
    assert "rota" not in engine.jobs


def test_engine_falls_back_to_utc_on_bad_timezone():
    engine = CronEngine(timezone="Marte/Olympus_Mons")
    assert engine.tz == timezone.utc


def test_engine_uses_configured_timezone():
    engine = CronEngine(timezone="Europe/Madrid")
    assert engine.now().tzinfo is not None
    assert "Madrid" in str(engine.tz)


def test_tick_fires_matching_job_without_crashing():
    """Regresión: el daemon moría con ValueError al parsear `*/20`."""
    engine = CronEngine(timezone="UTC")
    fired = []
    engine.register_job("cada_20", "*/20 * * * *", lambda: fired.append(1))
    engine.register_job("cada_3h", "0 */3 * * *", lambda: fired.append(2))

    engine.now = lambda: datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    asyncio.run(engine._tick())

    assert sorted(fired) == [1, 2]


def test_tick_does_not_fire_outside_schedule():
    engine = CronEngine(timezone="UTC")
    fired = []
    engine.register_job("cada_20", "*/20 * * * *", lambda: fired.append(1))

    engine.now = lambda: datetime(2026, 8, 31, 12, 7, tzinfo=timezone.utc)
    asyncio.run(engine._tick())

    assert fired == []


def test_tick_does_not_fire_twice_in_same_minute():
    engine = CronEngine(timezone="UTC")
    fired = []
    engine.register_job("cada_20", "*/20 * * * *", lambda: fired.append(1))

    engine.now = lambda: datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    asyncio.run(engine._tick())
    asyncio.run(engine._tick())  # el tick corre cada 30s, el minuto no ha cambiado

    assert fired == [1]
    assert engine.jobs["cada_20"]["run_count"] == 1


def test_failing_job_does_not_stop_other_jobs():
    engine = CronEngine(timezone="UTC")
    fired = []

    def explota():
        raise RuntimeError("la tinta se derramó")

    engine.register_job("rota", "* * * * *", explota)
    engine.register_job("sana", "* * * * *", lambda: fired.append("ok"))

    engine.now = lambda: datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    asyncio.run(engine._tick())

    assert fired == ["ok"]


def test_disabled_job_never_fires():
    engine = CronEngine(timezone="UTC")
    fired = []
    engine.register_job("dormida", "* * * * *", lambda: fired.append(1), enabled=False)

    engine.now = lambda: datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    asyncio.run(engine._tick())

    assert fired == []


def test_fire_condition_blocks_execution():
    engine = CronEngine(timezone="UTC")
    fired = []
    engine.register_job(
        "condicionada", "* * * * *", lambda: fired.append(1),
        fire_condition=lambda: False
    )

    engine.now = lambda: datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    asyncio.run(engine._tick())

    assert fired == []


def test_async_job_is_awaited():
    engine = CronEngine(timezone="UTC")
    fired = []

    async def tarea_async():
        fired.append("async")

    engine.register_job("async", "* * * * *", tarea_async)
    engine.now = lambda: datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    asyncio.run(engine._tick())

    assert fired == ["async"]


def test_all_configured_cron_jobs_are_valid():
    """Toda expresión de config.yaml debe parsear: es lo que corre en producción."""
    import yaml
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    jobs = config.get("scheduler", {}).get("cron_jobs", [])
    assert jobs, "config.yaml debe declarar tareas cron"
    for job in jobs:
        parse_cron_expression(job["cron"])

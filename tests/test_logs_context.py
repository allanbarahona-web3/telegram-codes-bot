import logging
import pytest
from services import db_service

@pytest.mark.asyncio
async def test_add_points_logs(caplog):
    user_id = 999999
    points = 10
    reason = "test-log-context"
    # Prepara el logger para capturar logs
    caplog.set_level(logging.INFO, logger="services.db_service")
    # Inserta usuario dummy
    await db_service.upsert_user(user_id, code="TESTLOG")
    # Ejecuta la función que debe loggear
    await db_service.add_points(user_id, points, reason)
    # Verifica que el log esperado esté presente
    logs = [r for r in caplog.records if r.levelname == "INFO" and f"Added {points} points to user {user_id}" in r.getMessage()]
    assert logs, "No se encontró el log esperado de add_points()"
    # Limpieza
    await db_service.delete_user(user_id)

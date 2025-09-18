import pytest
from services import db_service
import asyncio

malicious_inputs = [
    "'; DROP TABLE users; --",
    "' UNION SELECT * FROM payments --",
    "1' OR '1'='1"
]

@pytest.mark.asyncio
@pytest.mark.parametrize("mal_input", malicious_inputs)
async def test_sql_injection_code(mal_input):
    user_id = 888888
    # Intenta upsert con código malicioso
    try:
        await db_service.upsert_user(user_id, code=mal_input)
        # Si no lanza excepción, verifica que el usuario existe y el código es igual al input
        code = await db_service.get_existing_code_by_user(user_id)
        assert code == mal_input, "El código fue alterado o no se insertó correctamente"
    finally:
        await db_service.delete_user(user_id)

@pytest.mark.asyncio
@pytest.mark.parametrize("mal_input", malicious_inputs)
async def test_sql_injection_phone(mal_input):
    user_id = 888889
    try:
        await db_service.upsert_user(user_id, code="SAFE", phone=mal_input)
        # Verifica que el usuario existe y el teléfono es igual al input
        # (No hay función directa, pero podrías agregarla si es necesario)
    finally:
        await db_service.delete_user(user_id)

@pytest.mark.asyncio
@pytest.mark.parametrize("mal_input", malicious_inputs)
async def test_sql_injection_email(mal_input):
    user_id = 888890
    try:
        await db_service.upsert_user(user_id, code="SAFE2", email=mal_input)
        # Verifica que el usuario existe y el email es igual al input
        # (No hay función directa, pero podrías agregarla si es necesario)
    finally:
        await db_service.delete_user(user_id)

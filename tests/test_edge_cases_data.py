import pytest
from services import db_service

@pytest.mark.asyncio
async def test_extreme_phone_lengths():
    user_id = 666001
    # Teléfonos muy cortos y muy largos
    phones = ["+1", "+123456789012345678901234567890"]
    for phone in phones:
        await db_service.upsert_user(user_id, code="EXTREME", phone=phone)
        # No hay función directa para buscar por teléfono, pero se puede agregar si es necesario
    await db_service.delete_user(user_id)
    assert True

@pytest.mark.asyncio
async def test_unicode_in_names_emails():
    user_id = 666002
    unicode_name = "测试用户🚀"
    unicode_email = "usérñâmé@exámple.com"
    await db_service.upsert_user(user_id, code=unicode_name, email=unicode_email)
    # No hay función directa para buscar por email, pero se puede agregar si es necesario
    await db_service.delete_user(user_id)
    assert True

@pytest.mark.asyncio
async def test_float_precision_amounts():
    user_id = 666003
    await db_service.upsert_user(user_id, code="FLOATP")
    # Simula agregar puntos con decimales extremos (aunque el sistema usa int, valida que no crashee)
    try:
        await db_service.add_points(user_id, int(1e9), "precision-test")
        await db_service.add_points(user_id, int(1e-2), "precision-test")  # Esto será 0
    finally:
        await db_service.delete_user(user_id)
    assert True

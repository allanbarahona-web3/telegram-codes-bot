cat >> CHANGELOG.new <<EOF

## ${TAG} — ${DATE}
- Fix: “Compartir teléfono” → muestra código + menú.
- Fix: Detección de país por E.164 (sin ‘UNKN’ salvo indetectable).
- Add: Comandos por idioma (ES/EN) en BotFather.
- Add: /help + botón “Volver al menú”.
- Chore: separar entornos (DEV .env.dev / QA .env) y DBs por entorno.
### Added
- Referrals core: unique codes, anti-abuse validations, self-referral blocked, group access with TTL.
- Balance and payouts: balance queries, withdrawal requests, payment records.
- Admin: CSV export, manual referral approvals, notifications.
- Bilingual support (English/Spanish).
- Flexible `.env` configuration: currency, commission, default region.

### QA
- Freeze created with tag `v0.1.0` for execution in Qase (Test Run #1).
- Tester assigned: Karen (Admin role in Qase).


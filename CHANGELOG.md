# Changelog

## v1.0.0-qa — 2025-09-18

### Added
- Referral logic: unique codes, anti-abuse validations, self-referral blocked, group access with TTL.
- Balance and payouts: balance queries, withdrawal requests, payment records.
- Admin: CSV export, manual referral approvals, notifications.
- Bilingual support (English/Spanish).
- Flexible `.env` configuration: currency, commission, default region, etc.

### Fixed
- "Share phone" now shows code and menu correctly.
- Country detection by E.164 (only UNKN if undetectable).
- Language-specific commands (EN/ES) in BotFather.
- /help and "Back to menu" button.
- Environment separation (DEV .env.dev / QA .env) and DBs per environment.

### QA & Automated Tests
- Freeze created with tag `v1.0.0-qa` for QA execution.
- Automated test coverage:
  - SQL Injection in inputs (codes, phones, emails)
  - Concurrency in registration and withdrawals
  - Resource limits (connection pool, long messages)
  - Data edge cases (Unicode, length, precision)
  - Referral logic, withdrawals, campaigns, payment methods, i18n, logs, migrations, etc.
- Tester assigned: Karen (Admin role in Qase).

---
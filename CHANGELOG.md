# Changelog

## v1.0.0-qa (2025-09-22)

### Added
- Column `account` in the `payments` table to record the exact PayPal email or Binance Pay ID used for each withdrawal.
- Support for withdrawals via PayPal and Binance Pay, with confirmation and exact account/ID registration.
- Robust handlers for the entire withdrawal, points, and referral flow.
- Commands `/mypoints`, `/balance`, `/withdraw`, `/mycode`, `/mylink`, `/group`, `/id` and their Spanish variants.
- Inline buttons for payout method selection and confirmation.
- Temporary dictionary to handle requested withdrawal amount per user.
- Code cleanup to avoid duplicates and repeated handlers.

### Changed
- Improved payout method logic: each withdrawal is now linked to the exact account/ID used, even if the user changes their method later.
- Refactored handlers and services for clarity and robustness.
- Improved database structure and service access logic.

### Fixed
- Issue with payout method overwriting when requesting withdrawals to different accounts.
- Indentation and duplication errors in service and handler files.

---

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
- Freeze created with tag `qa-20250923-1 ` for QA execution.
- Automated test coverage:
  - SQL Injection in inputs (codes, phones, emails)
  - Concurrency in registration and withdrawals
  - Resource limits (connection pool, long messages)
  - Data edge cases (Unicode, length, precision)
  - Referral logic, withdrawals, campaigns, payment methods, i18n, logs, migrations, etc.
- Tester assigned: Karen (Admin role in Qase).

---

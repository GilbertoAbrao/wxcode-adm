---
phase: 05-platform-security
plan: "03"
subsystem: email
tags: [fastapi-mail, jinja2, html-email, smtp, templates, transactional-email]

# Dependency graph
requires:
  - phase: 02-auth-core
    provides: send_verification_email and send_reset_email stubs in auth/email.py
  - phase: 03-multi-tenancy-and-rbac
    provides: send_invitation_email stub in tenants/email.py
  - phase: 04-billing-core
    provides: send_payment_failed_email stub in billing/email.py
provides:
  - shared FastMail singleton in common/mail.py with TEMPLATE_FOLDER configured
  - 9 branded email templates (1 base layout + 4 HTML + 4 plain-text) in templates/email/
  - all 4 email sender functions upgraded from plain-text stubs to multipart HTML+plain-text
affects: [06, 07, testing, smtp-configuration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared FastMail singleton pattern: constructed once at module load, imported lazily inside try/except by senders"
    - "Jinja2 template inheritance: 4 HTML templates extend base.html via {% extends %}"
    - "Multipart email: html_template + plain_template params produce alternative MIME parts"
    - "Table-based email layout with inline CSS for email client compatibility"
    - "WXCODE brand tokens: header #18181b, CTA #3b82f6, body #27272a, muted #71717a, bg #f4f4f5"

key-files:
  created:
    - backend/src/wxcode_adm/common/mail.py
    - backend/src/wxcode_adm/templates/email/base.html
    - backend/src/wxcode_adm/templates/email/verify_email.html
    - backend/src/wxcode_adm/templates/email/verify_email.txt
    - backend/src/wxcode_adm/templates/email/reset_password.html
    - backend/src/wxcode_adm/templates/email/reset_password.txt
    - backend/src/wxcode_adm/templates/email/invitation.html
    - backend/src/wxcode_adm/templates/email/invitation.txt
    - backend/src/wxcode_adm/templates/email/payment_failed.html
    - backend/src/wxcode_adm/templates/email/payment_failed.txt
  modified:
    - backend/src/wxcode_adm/auth/email.py
    - backend/src/wxcode_adm/tenants/email.py
    - backend/src/wxcode_adm/billing/email.py

key-decisions:
  - "FastMail singleton constructed at module load in common/mail.py, imported lazily inside try/except by senders — avoids import errors when SMTP is not configured"
  - "Used html_template + plain_template params (not template_name) so fastapi-mail produces proper multipart/alternative MIME structure with both HTML and plain-text parts"
  - "Templates use {{ variable }} directly (not {{ body.variable }}) — fastapi-mail 1.6.2 passes template_body dict at top level via render(**template_data)"
  - "Table-based layout with inline CSS only — no <style> blocks since email clients strip them"

patterns-established:
  - "Email template pattern: HTML extends base.html, .txt is standalone plain-text, both passed as html_template + plain_template"
  - "Sender pattern: [DEV] log first, then lazy import fast_mail inside try/except, send with html_template + plain_template"

requirements-completed: [PLAT-05]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 05 Plan 03: Branded Email Templates Summary

**Shared FastMail singleton + 9 Jinja2 email templates replacing plain-text SMTP stubs for all 4 transactional emails (verify, reset, invite, payment_failed)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T14:11:25Z
- **Completed:** 2026-02-24T14:14:45Z
- **Tasks:** 2
- **Files modified:** 13 (10 created, 3 modified)

## Accomplishments

- Created shared `common/mail.py` FastMail singleton with `TEMPLATE_FOLDER` pointing to `templates/email/`
- Built 9 email templates: `base.html` (WXCODE branded table layout), 4 HTML templates extending base, 4 plain-text fallbacks
- Refactored all 4 email sender functions in `auth/email.py`, `tenants/email.py`, and `billing/email.py` to use the shared singleton with `html_template` + `plain_template` multipart sending
- Eliminated per-call `ConnectionConfig` + `FastMail(conf)` construction from all 3 email modules

## Task Commits

Each task was committed atomically:

1. **Task 1: Create FastMail singleton and all 9 email template files** - `77c8d94` (feat)
2. **Task 2: Refactor all 4 email sender functions to use templates** - `61ace14` (feat)

**Plan metadata:** `[pending docs commit]` (docs: complete plan)

## Files Created/Modified

- `backend/src/wxcode_adm/common/mail.py` - Shared FastMail singleton, TEMPLATE_FOLDER configured
- `backend/src/wxcode_adm/templates/email/base.html` - Branded Jinja2 base layout (WXCODE header #18181b, content block, footer)
- `backend/src/wxcode_adm/templates/email/verify_email.html` - OTP code in styled 32px block
- `backend/src/wxcode_adm/templates/email/verify_email.txt` - Plain-text OTP fallback
- `backend/src/wxcode_adm/templates/email/reset_password.html` - CTA button + fallback link
- `backend/src/wxcode_adm/templates/email/reset_password.txt` - Plain-text reset link
- `backend/src/wxcode_adm/templates/email/invitation.html` - Workspace name, role, accept CTA
- `backend/src/wxcode_adm/templates/email/invitation.txt` - Plain-text invite
- `backend/src/wxcode_adm/templates/email/payment_failed.html` - Warning heading, amber accent, billing CTA
- `backend/src/wxcode_adm/templates/email/payment_failed.txt` - Plain-text payment failed
- `backend/src/wxcode_adm/auth/email.py` - Refactored: fast_mail singleton, html/plain templates, no per-call ConnectionConfig
- `backend/src/wxcode_adm/tenants/email.py` - Refactored: fast_mail singleton, invitation templates
- `backend/src/wxcode_adm/billing/email.py` - Refactored: fast_mail singleton, payment_failed templates

## Decisions Made

- **FastMail singleton**: Constructed once at module load in `common/mail.py`, imported lazily inside `try/except` by each sender — avoids import errors when SMTP is not configured in dev/test environments.
- **html_template + plain_template params**: Used the two-param variant of `send_message()` (not `template_name`) so fastapi-mail produces proper `multipart/alternative` MIME structure with both HTML and plain-text parts simultaneously.
- **Template variable syntax**: `{{ variable }}` directly (not `{{ body.variable }}`) — fastapi-mail 1.6.2 passes `template_body` dict at top level via `render(**template_data)`.
- **Inline CSS only**: All CSS is inline (`style="..."`), no `<style>` blocks — email clients strip `<style>` tags so inline is required for visual correctness.

## Deviations from Plan

None — plan executed exactly as written.

The plan specified `html_template` as the parameter name in `send_message()`, which matches the actual fastapi-mail 1.6.2 API exactly (verified against installed source at `/Users/gilberto/.pyenv/versions/3.12.3/lib/python3.12/site-packages/fastapi_mail/fastmail.py`).

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. SMTP settings already configured via Phase 2 `SMTP_*` environment variables.

## Next Phase Readiness

- All 4 transactional emails now send branded HTML+plain-text multipart emails
- FastMail singleton is the canonical way to send emails in this project
- Ready for Phase 6 (TOTP/2FA) and Phase 7 (frontend integration) which may add additional email types following the same pattern

## Self-Check: PASSED

All 14 files verified to exist on disk. Both task commits (77c8d94, 61ace14) and metadata commit (35353c0) verified in git log.

---
*Phase: 05-platform-security*
*Completed: 2026-02-24*

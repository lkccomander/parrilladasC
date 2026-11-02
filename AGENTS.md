# Project conventions

Read `docs/architecture.md`, `docs/implementation-plan.md` and `proyect_brain/TECH_STACK_MVP.md` before changing the application.

- Deploy Admin (`parrilladas.admin`) and API (`parrilladas.main`) as separate services. Admin calls API over HTTP with Bearer JWT; only API has database credentials and the JWT signing key.
- Dashboard code may import contracts/schemas, never business services, repositories or ORM models. Keep CSRF validation on forms and API mutations.
- Keep Python code under `backend/src/parrilladas` in feature modules.
- Routes handle HTTP; services own use cases and explicit transactions; repositories own SQL. Add layers only when behavior needs them.
- Do not put business rules in `main.py`, dashboard templates or external adapters.
- Use module services/contracts for cross-module operations. Do not reach into another module's repositories or routers.
- New models must be registered in `db/models.py` and accompanied by a reviewed Alembic migration. Never use `create_all` on application startup.
- Use Decimal for money, timezone-aware operational timestamps, and explicit data validation.
- Enforce Admin/Sales permissions on the server. Business endpoints must not be exposed before authentication and CSRF protection are implemented.
- Prices are manual. Approval and sending are separate actions. Changed quotes need renewed approval. Follow-up is an internal reminder, never an automatic customer message.
- Keep live WhatsApp credentials and customer data out of fixtures, logs and Git. Never read or publish local credential notes unless specifically needed.
- Google Calendar and AI are deferred beyond launch.
- Run `ruff check backend`, `ruff format --check backend`, `pytest backend/tests` and `python -m pip check` with the project environment active.
- PostgreSQL migration tests use only an empty, disposable database via `TEST_DATABASE_URL`; never use a business database.
- Follow lock-file update commands in the README and validate packaging after dependency changes.

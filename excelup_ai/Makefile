# ExcelUp AI - all-in-one commands (run from the project folder).
# On Windows without `make`, run the underlying commands directly (see README).

.PHONY: reset seed warmup test backend frontend install

install:
	cd backend && python -m venv .venv && .venv\\Scripts\\python -m pip install -r requirements.txt
	cd frontend && npm install

# Drop, recreate and reseed the remote Neon DB (bulk inserts, < 5 min)
reset:
	cd backend && python -m seed.run --reset

seed:
	cd backend && python -m seed.run

# Keep Neon awake (runs forever; useful before a demo session)
warmup:
	cd backend && python -m seed.warmup

test:
	cd backend && python -m pytest tests -q

backend:
	cd backend && .venv\\Scripts\\python -m uvicorn app.main:app --reload

frontend:
	cd frontend && npm run dev

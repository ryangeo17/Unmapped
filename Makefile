.PHONY: install test build api web

install:
	python3 -m pip install -r backend/requirements.txt
	cd frontend && npm install

test:
	cd backend && python3 -m pytest
	cd frontend && npm test

build:
	cd frontend && npm run build

api:
	cd backend && uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

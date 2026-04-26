.PHONY: test test-cov lint typecheck all

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ -v --cov=video_maker --cov-fail-under=80 --cov-report=term-missing

lint:
	ruff check .

typecheck:
	mypy video_maker/ --ignore-missing-imports

all: lint typecheck test-cov

# ParkingBot

A Python side project.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt for runtime only
cp .env.example .env                  # then fill in your values
```

## Run

```bash
python src/parkingbot/main.py
```

## Test & lint

```bash
pytest
ruff check .
```

## Layout

```
src/parkingbot/   # package code
tests/            # pytest tests
requirements.txt  # runtime deps  (requirements-dev.txt adds test/lint tooling)
```

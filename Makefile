.PHONY: mcp-smoke mcp-test

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

mcp-test:
	$(PYTHON) -m pytest tests/test_mcp_server.py -q

mcp-smoke:
	$(PYTHON) scripts/mcp_personal_smoke.py

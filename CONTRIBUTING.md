# Contributing to OnionQuant

Thanks for your interest in contributing! This document outlines the process and conventions.

## Getting Started

1. Fork the repo and clone your fork
2. Create a branch: `git checkout -b feature/your-feature-name`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Make your changes
5. Run tests: `pytest tests/ -v`
6. Lint: `ruff check . && ruff format --check .`
7. Commit and push
8. Open a Pull Request

## Code Style

- Python 3.12+
- Type hints required for all public functions
- Docstrings follow Google style for public APIs
- Line length: 100 characters
- Formatter: `ruff format` (configured in `pyproject.toml`)
- Linter: `ruff check` (rules: E, F, I, N, W, UP)

## Commit Convention

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — adding or updating tests
- `security:` — security improvements or sensitive data removal
- `chore:` — maintenance tasks

Example:
```
feat: add HMM regime detection with 3-state Markov Switching

Implements Hamilton (1989) Markov Switching model for bull/bear/sideways
regime classification. Adds regime_detector.py to quant_framework/strategies/.

Closes #42
```

## Testing

- New features should include tests
- Run full suite before opening PR: `pytest tests/ -v`
- Tests use `pytest` with fixtures in `tests/conftest.py`

## Security

- **Never** commit API keys, passwords, or tokens
- Use environment variables (`os.getenv()`) for all credentials
- The pre-commit hook scans for secrets automatically
- If you accidentally commit a secret: rotate it immediately and notify maintainers

## Pull Request Process

1. Update documentation if the change affects public APIs
2. Add an entry to the PR description explaining what and why
3. Ensure CI passes
4. A maintainer will review within 2-3 days

## Areas for Contribution

| Area | Difficulty | Impact |
|------|-----------|--------|
| Factor computation unit tests | Beginner | High |
| Documentation improvements | Beginner | Medium |
| Additional data source integrations | Intermediate | High |
| Backtesting framework enhancements | Advanced | Medium |
| Agent orchestration patterns | Advanced | High |
| Knowledge graph expansion | Intermediate | Medium |

## Questions?

Open an issue with the `question` tag or start a discussion.

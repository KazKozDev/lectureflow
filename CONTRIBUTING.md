# Contributing to LectureFlow

## How to Contribute

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Commit using conventional format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
4. Push and open a Pull Request

## Code Style

This project uses [Black](https://github.com/psf/black) (line length 88) and [Ruff](https://github.com/astral-sh/ruff) for linting. Format your code before committing:

```bash
black src/ tests/
ruff check src/ tests/ --fix
```

## Tests

Run the test suite before submitting:

```bash
pytest
```

## Issues

Use GitHub issue templates for bug reports and feature requests.

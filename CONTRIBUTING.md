# Contributing to HOPEtensor

Thanks for your interest in contributing to **HOPEtensor**.

This project is in active development, and outside contributions are welcome.

## Ways to Contribute

- Report bugs and unclear behavior.
- Propose architecture or documentation improvements.
- Add tests and reliability checks.
- Improve developer experience (tooling, setup, CI, examples).
- Open pull requests for focused code/documentation changes.

## Before You Start

1. Read `readme.md` for project context.
2. Review related docs under:
   - `docs/whitepaper/`
   - `docs/techspec/`
3. Prefer small, focused PRs over large multi-topic changes.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the main service locally:

```bash
python app/main.py
```

## Contribution Workflow

1. Fork the repository.
2. Create a feature branch:

   ```bash
   git checkout -b feat/short-description
   ```

3. Implement your change with clear commit messages.
4. Run relevant tests/checks before opening a PR.
5. Open a pull request with:
   - Problem statement
   - Proposed change
   - Validation steps
   - Risks / limitations

## Pull Request Guidelines

- Keep scope limited to one logical change.
- Update docs when behavior or architecture changes.
- Avoid unrelated formatting-only edits.
- Include exact commands used for validation.

## Commit Message Suggestions

Use a simple conventional style:

- `feat: add ...`
- `fix: correct ...`
- `docs: update ...`
- `refactor: simplify ...`
- `test: add ...`

## Code Quality Expectations

- Write readable, explicit code.
- Prefer deterministic behavior and clear failure modes.
- Protect safety-sensitive logic with checks.
- Keep functions focused and easy to review.

## Reporting Security Issues

If you discover a security-sensitive issue, please avoid public disclosure in an issue.
Instead, open a private channel with maintainers if available.

---

**Principle:** _Just Kindness, Nothing Else._

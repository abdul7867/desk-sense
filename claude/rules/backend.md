---
paths:
  - "**/*.py"
description: Python/backend conventions. Loads only when touching Python files.
---

# Backend rules

Edit this file to match your project. Delete what does not apply — every line here
is context cost whenever a Python file is in play.

## Types and structure
- Type-annotate every public function signature. Run the project's type checker
  before declaring done.
- Prefer explicit dataclasses or Pydantic models over passing bare dicts across
  module boundaries.
- Keep I/O at the edges: pure logic in functions that take and return values, so it
  is testable without mocks.

## Errors
- Never `except:` or `except Exception:` without re-raising or logging with context.
- Raise specific exceptions. A caller cannot handle `Exception`.
- Validate inputs at the boundary (request handlers, CLI entry points, queue
  consumers) — not deep in the call stack.

## Security
- No secrets in code or committed config. Read from the environment.
- Parameterize every query. No string-built SQL.
- New endpoints state their authentication and authorization explicitly; "inherits
  from the router" must be verified, not assumed.

## Tests
- `pytest`. Unit tests for logic, integration tests for anything crossing a process
  or network boundary.
- Test the failure paths, not only the happy path.
- Every bug fix gets a test that fails before the fix.

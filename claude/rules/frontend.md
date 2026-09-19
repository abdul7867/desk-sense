---
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.css"
description: Frontend conventions. Loads only when touching frontend files.
---

# Frontend rules

Edit this file to match your project. Delete what does not apply — every line here
is context cost whenever a frontend file is in play.

## Types
- No `any`. Use `unknown` plus a narrowing check when the shape is genuinely unknown.
- No new `@ts-expect-error` or `@ts-ignore` without a comment saying why and what
  would remove it.
- Prefer inferred return types; annotate exported function signatures.

## React
- Server Components by default; add `"use client"` only when the component needs
  state, effects, or browser APIs.
- No `useEffect` for derived state — compute it during render.
- Every list item needs a stable `key` that is not the array index.
- Data fetching belongs in the server layer or a query library, not in bare effects.

## Errors and loading
- Every async boundary has a loading state and an error state. A spinner that never
  resolves on failure is a bug, not a gap.
- Do not swallow errors in a `catch` — log or surface them.

## Accessibility
- Interactive elements are real `button`/`a` elements, or carry a role plus keyboard
  handlers.
- Every input has an associated label. Every image has `alt` (empty `alt=""` if decorative).
- Do not remove focus outlines without replacing them with a visible alternative.

## Tests
- Test behavior through the rendered output, not implementation details.
- Every bug fix gets a test that fails before the fix.

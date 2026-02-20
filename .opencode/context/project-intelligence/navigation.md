<!-- Context: project-intelligence/navigation | Priority: high | Version: 1.2 | Updated: 2026-02-20 -->

# Project Intelligence

**Purpose**: Quick navigation to all project intelligence files.
**Last Updated**: 2026-02-20

## Files

| File | Description | Priority |
|------|-------------|----------|
| technical-domain.md | Tech stack, code patterns, naming, security | critical |

## Quick Routes
- **Tech stack?** → technical-domain.md § Primary Stack
- **How to write a view?** → technical-domain.md § Code Patterns
- **How to write a form?** → technical-domain.md § Code Patterns → Forms
- **Registration pattern?** → technical-domain.md § Code Patterns → Registration
- **Dual-form editing?** → technical-domain.md § Code Patterns → Dual-Form Editing
- **Auth views?** → technical-domain.md § Code Patterns → Auth Views
- **Naming rules?** → technical-domain.md § Naming Conventions
- **Security checklist?** → technical-domain.md § Security Requirements
- **What files exist?** → technical-domain.md § Codebase References
- **Project structure?** → technical-domain.md § Project Structure
- **Testing setup?** → technical-domain.md § Testing Architecture
- **Test factories?** → technical-domain.md § Testing Architecture → Factories
- **How to run tests?** → technical-domain.md § Testing Architecture → Running Tests

## Implementation Status
| Module | Models | Forms | Views | URLs | Templates | Admin | Tests | Migrations | Status |
|--------|--------|-------|-------|------|-----------|-------|-------|------------|--------|
| accounts | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 26 | ✅ | **Done** |
| requests | ✅ | — | — | — | — | ✅ | ✅ 17 | ✅ | Models + Admin + Tests |
| reviews | ✅ | — | — | — | — | ✅ | ✅ 6 | ✅ | Models + Admin + Tests |
| notifications | ✅ | — | — | — | — | ✅ | ✅ 5 | ✅ | Models + Admin + Tests |
| stats | — | — | — | — | — | — | — | ✅ | Placeholder |

**Total: 54 tests passing** (pytest + factory_boy, ~3s on SQLite in-memory)

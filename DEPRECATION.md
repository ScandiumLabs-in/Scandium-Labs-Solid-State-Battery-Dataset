# Deprecation Policy — SSB Dataset

## Principles

1. **No silent removal.** Every removed or renamed field goes through a
   documented deprecation cycle.
2. **One-release notice.** Fields slated for removal are marked deprecated
   in one MINOR release and removed in the next MAJOR release.
3. **Migration path.** Deprecated fields include a recommended replacement
   and codemod instructions.

## Deprecation Lifecycle

| Phase | Status | Action |
|-------|--------|--------|
| Active | `active` | Fully supported |
| Deprecated | `deprecated` | Still present but emits a warning; slated for removal |
| Removed | `removed` | Field no longer exists in schema |

## Current Deprecations (v0.1.0)

None. This is the initial release.

## How to Deprecate a Field

1. Open a GitHub issue with the deprecation proposal.
2. Add `_deprecated` suffix in the schema (or add `deprecated=True` metadata).
3. Update all documentation to reference the replacement.
4. Add a runtime warning when the field is accessed.
5. Remove in the next MAJOR release.

## Exceptions

- Fields that expose a security vulnerability may be removed immediately
  with a PATCH release.
- Fields that were never documented or populated may be removed without
  deprecation.

## Contact

For questions about this policy: https://github.com/ScandiumLabs-in/Scandium-Labs-Solid-State-Battery-Dataset/issues

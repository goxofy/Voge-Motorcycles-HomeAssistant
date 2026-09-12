## Summary

Describe the user-visible and internal changes.

## Read-only and privacy checklist

- [ ] Every cloud request remains on a statically declared read-only allowlist.
- [ ] No vehicle, account, binding, notification, message, firmware, or marketplace state is modified.
- [ ] No arbitrary URL, HTTP method, path, or query escape hatch was added.
- [ ] Tests and documentation contain no real credentials, password hashes, tokens, VINs, complete identifiers, precise locations, message contents, raw responses, or signing material.
- [ ] Modern `productId` is not treated as booking/marketplace `modelCode` or as a proven capability identifier.
- [ ] New vehicle fields are gated by server capability data or a validated non-empty value.

## Validation

- [ ] Tests pass with the supported Home Assistant/Python baseline.
- [ ] Ruff passes.
- [ ] Pyright passes.
- [ ] HACS validation and Hassfest pass.
- [ ] Documentation and translations were updated where needed.

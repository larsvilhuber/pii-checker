# PII Checker — instructions for AI coding agents

## Versioning (required on every change)

The version lives in `version.py` (`__version__`) and follows
[semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

Bump it **in the same commit** as the change, and name the new version in the
commit message:

- **PATCH** — bug fix, doc/comment change, refactor with no behaviour change.
- **MINOR** — new feature: a new command-line flag, a new supported file
  format, a new output column, new configuration key, or any other change a
  user can notice without anything breaking.
- **MAJOR** — breaking change: removing/renaming a CLI flag, a `config.env`
  key, or an output column; changing the meaning of an existing evaluation
  category; anything that makes an existing invocation or downstream reader of
  `ai_pii_check.xlsx` / `ai_pii_results_overview.xlsx` stop working.

While the version is `0.x.y`, treat MINOR as the "feature" counter and PATCH
as the "fix" counter; a MAJOR bump to `1.0.0` is a deliberate decision by the
maintainer, not something to do unprompted.

## Tests

`python -m pytest -q test_model_select.py` — run before committing.

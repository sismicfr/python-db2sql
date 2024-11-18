<!--
Thanks for contributing to db2sql! Please fill the sections below — empty PRs
are harder to review and tend to stall.
-->

## Summary

<!-- One paragraph: what does this PR change and why? Focus on motivation, not
     a play-by-play of the diff (the diff is right there). -->

## Type of change

- [ ] Bug fix (`fix:`) — non-breaking change that fixes an issue
- [ ] Feature (`feat:`) — non-breaking change that adds capability
- [ ] Performance (`perf:`)
- [ ] Refactor (`refactor:`) — no behaviour change
- [ ] Documentation (`docs:`)
- [ ] CI / build / tooling (`ci:` / `chore:`)
- [ ] **Breaking change** — describe the migration path below

## Linked issues

<!-- "Fixes #123", "Refs #456", … -->

## How was this tested?

<!-- For non-trivial changes, describe the test plan. New tests? Manual run
     against the docker stack? Tested on which DB versions? -->

- [ ] `pytest tests/unit tests/cli` passes locally
- [ ] `lint-imports` passes (no driver leaked into domain/application)
- [ ] `tox -e syntax` passes (black, isort, flake8, mypy, pylint)
- [ ] For changes touching readers/writers/emitters: `tests/functional` ran against the docker stack

## Checklist

- [ ] Commit messages follow the Conventional Commits / Angular preset
      (`feat:`, `fix:`, `chore:` …) — `semantic-release` relies on this
- [ ] Public API changes are documented in `docs/` and `CHANGELOG.md`
- [ ] Coverage is maintained at or above the current threshold (80%)
- [ ] No credentials, hostnames, or other sensitive data leaked in tests / fixtures
- [ ] If this is a breaking change, the README / docs migration notes are updated

## Notes for the reviewer

<!-- Anything that's easy to miss: subtle invariants you preserved, places
     where you considered an alternative and rejected it, follow-up work
     intentionally left out of this PR, etc. -->

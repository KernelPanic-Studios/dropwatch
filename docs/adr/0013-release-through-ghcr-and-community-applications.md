# ADR-0013: Publish the image to GitHub's registry from tags, and list it through Community Applications

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

Dropwatch is made for Unraid. `docs/development.md` records the choice of 2026-10-11: one registry,
published by the same workflow that runs the tests, with no extra account or token; Docker Hub is
deliberately not used.

## Decision

The `docker` workflow (`.github/workflows/docker.yml`) runs on a `v*` tag: Python tests, web type check
and tests, then builds `linux/amd64` and pushes `ghcr.io/kernelpanic-studios/dropwatch:<version>` and
`:latest`, passing `DROPWATCH_COMMIT=<tag>@<sha>`. Unraid's Community Applications reads
`unraid/dropwatch.xml` and `ca_profile.xml` from `main`, so template text changes need no tag.

## Consequences

- An image is published only after its tests pass.
- **Only `linux/amd64` is built.**
- `:latest` moves on every tag; operators who want to stay on a version pin the version tag.
- Lint is not part of the gate (finding F5).
- **A manual run (`workflow_dispatch`) publishes too:** the version becomes the branch name and `:latest`
  moves to that build (finding F3).

## Evidence

`.github/workflows/docker.yml`, `unraid/dropwatch.xml`, `ca_profile.xml`, `docs/development.md`
(Releasing); commit `bd184b9`.

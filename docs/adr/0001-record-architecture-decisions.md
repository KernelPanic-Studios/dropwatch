# ADR-0001: Record architecture decisions

**Status:** Accepted, 2026-11-15

## Context

Dropwatch's reasons live in commit messages, code comments ("asked for 2026-10-11", "review fix"), the
original spec in `docs/superpowers/specs/` and the approved mockups in `docs/design/`. The spec is a record
of the plan at the time and has drifted (see the divergence table in
[architecture/README.md](../architecture/README.md#where-the-docs-diverged-from-the-code)). A contributor
who wants to know why something is shaped the way it is has to read all of it.

## Decision

Keep one file per decision in `docs/adr/`, named `NNNN-kebab-case-title.md`, with the headings **Status**,
**Context**, **Decision**, **Consequences** and **Evidence**. A record is never rewritten once accepted: a
new record supersedes it, and the old one's status says "Superseded by ADR-NNNN". A record proposed in a
pull request has the status `Proposed` until the pull request merges, then `Accepted, YYYY-MM-DD`.

Records 0002 to 0013 were written on 2026-11-15 from the code and history and are marked "recorded
retroactively". Where the code does not say why, the record says what the code shows and leaves the motive
out.

## Consequences

- A decision that a later contributor could reasonably undo without knowing why gets a record.
- The index in [README.md](README.md) is updated in the same change as a new record.

## Evidence

`docs/adr/README.md`, the rule in `docs/development.md` (Keeping the docs current).

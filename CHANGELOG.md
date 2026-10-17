# Changelog

## 0.5.0

- New check `workflow-permissions`. A workflow that calls another workflow of the same repo must hold every permission the called one asks for. When it does not, GitHub refuses to start the whole run with no jobs and no log (hearth's v0.5.5 release stayed empty). actionlint does not know this rule. It needs only Python, runs with the other whole-tree checks, and has one optional setting for the repo's default token.
- Tagging `vX.Y.Z` now publishes the release page by itself, after the tests pass and the tag matches `VERSION`.

## 0.4.0

GitHub is now the home of agent-checks. `tools/vendor` clones from here and records the source and commit in each repo's pinned copy. The repo runs its own tests on GitHub Actions.

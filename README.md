# agent-checks

Small checks that make the common agent mistakes impossible instead of something to remember. One home for the scripts, so
the helv-io repos never drift apart. This repo is the home; the repos that use it each carry a pinned copy.

Each check says what is wrong and how to fix it, so an agent can repair its own change without a person in the loop.

## Checks

| Check | Stops | Where it runs |
|---|---|---|
| `identity` | A commit by anyone but Helvio Pedreschi `<helvio88@gmail.com>` (bots and listed outside contributors are fine) | every pull request and push |
| `voice` | Em dashes, marketing words, repo-specific jargon in text people read. Added lines only on a change, whole tree weekly | every pull request and push, weekly |
| `docs` | User-facing code changed but README or CHANGELOG did not (`Docs: skip <reason>` in a commit message opts out) | every pull request and push |
| `model-ids` | A built-in model name in shipped code | every pull request and push |
| `private` | Personal names or private hostnames in a public repo. Names are stored as hashes (`agent-checks private-hash Name`), or in a local list that is never in the repo | every pull request and push |
| `release-version` | A tag whose version does not match the files that repeat it. Run before anything is published | first job of a release |
| `release-assets` | A release page with a missing file. Run after publishing | last job of a release |
| `nightly-alert` | A scheduled run that fails with nobody watching: opens one issue, closes it when green again | last job of scheduled workflows |
| `no-skips` | A test run that is green only because tests were skipped | the repo's one test command |
| `verify` | A hand-edited copy of these checks inside a repo | first step of the job |
| `actionlint` | A broken workflow file (the ha-supergrok nightly was red for six weeks) | every pull request and push |

Every check was written for a real past mistake and `tests/test_checks.py` proves it on that mistake and on the fixed version.

## Use in a repo

Each repo carries a pinned copy of the checks in `.agent-checks/`, with a manifest of file hashes, the commit it came from
(`REF`) and where that commit lives (`SOURCE`). CI runs that copy, so it needs nothing from the network and always runs the
reviewed version. The `verify` step fails when the copy was edited by hand, so repos cannot drift apart.

1. `tools/install <repo> [checkout version]` writes `.github/workflows/agent-checks.yml` and `.agent-checks/`. Commit both.
2. To update a repo later: change the checks here, merge, then run `tools/vendor <repo>...` and commit the new `.agent-checks/` in each repo. `tools/vendor` always copies from a fresh clone of this GitHub repo (latest main, or `--ref TAG`), so the recorded commit is one anyone can fetch.
3. Locally, in the repo: `.agent-checks/bin/agent-checks local` (or put `bin/agent-checks` on your PATH). It runs what CI runs
   against the remote default branch.
4. Optional settings go in `.agent-checks.toml` at the repo root (below). Other jobs (a release gate, a scheduled alert) call
   `python3 .agent-checks/bin/agent-checks <command>`.

## Settings (`.agent-checks.toml`)

```toml
[identity]
allow-emails = ["outside.contributor@example.com"]   # real outside contributors already in the history

[voice]
skip = ["^docs/archive/"]                            # paths that are not prose
[[voice.extra]]
pattern = "(?i)\\bthe host\\b"
why = "jargon"
fix = "say 'the computer'"
paths = "\\.qml$|^README\\.md$"                  # optional: only these files

[docs]
user-facing = "^(src|app)/"                          # what counts as user-facing
require = ["CHANGELOG.md", "README.md"]

[model-ids]
exempt = ["^legacy/"]

[private]
required = false                                     # true: a missing word list fails (use on your own machine)
[[private.allow]]
path = "^tests/fixtures/"
why = "the fixture needs a realistic name"

[[release.version]]                                  # every file that repeats the version, one capture group each
file = "internal/config/config.go"
pattern = 'const Version = "([^"]+)"'

[no-skips]
allow = ["^SKIPPED .* Windows only"]
```

Exceptions on a line expire: `voice-ok: <reason> until 2027-01-31`, `model-id-ok: <reason> until 2027-01-31`.
No reason or a past date fails the check, so an exception cannot be forgotten.

Private words come from three places: `[private] hashes` (sha256 of a lowercase name; keeps it out of plain sight, but someone who
guesses the name can confirm it), `[private] patterns` (words that are not secret, such as a domain), and a local list in the
`AGENT_CHECKS_PRIVATE_WORDS` variable or `~/.config/agent-checks/private-words` (one pattern per line, never in a repo).

## Develop

The only copy that counts is this GitHub repo. A mirror on another server is read only.

`tools/test` is the one command CI also runs. A skipped test counts as a failure.

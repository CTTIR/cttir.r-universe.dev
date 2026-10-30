# Registry maintenance — 2026-10-30

This repository tells R-universe which public CTTIR package repositories to
build. Its principal journeys are a correct registry change and installation
from the resulting published package index. Package scientific correctness and
proprietary SDK qualification belong to the individual package audits.

The original checkout is clean at `ba4e69681c7e37032a22129b53e7d770d837ae1f`.
The isolated maintenance branch starts at the newer remote `40894cf`, preserving
the existing additions of cellspecR and songR. All six package entries match
their public, unarchived GitHub repositories and DESCRIPTION package names.
R-universe currently reports successful source builds at those upstream commits;
all 60 returned binary records have successful build status. This is dated
remote evidence, not a guarantee of future builds or scientific correctness.

## Findings and strategy

1. **Maintenance gap:** no CI or validation protects `packages.json`. Add a
   dependency-free validator and meaningful malformed-registry regressions.
   Require unique valid package names, approved public repository URLs, safe
   optional branch/subdirectory fields and strict JSON. An explicit read-only
   upstream check must confirm public repository and package identity.
2. **Documentation defect:** registration is described as immediate publication,
   and a pure-R package is called fully functional without qualification.
   Explain asynchronous builds, failures, SDK limitations and provenance checks.
3. **Release limitation:** this repository has no explicit license. Do not infer
   one from its package repositories; a maintainer license decision remains
   necessary before claiming permission to redistribute the registry tooling.

Acceptance: the unchanged six-entry registry passes local and upstream checks;
invalid identities, ambiguous JSON and unsafe inputs fail; CI syntax validates;
the documented R installation path works in an isolated library. Preserve the
package list and default-branch tracking. Do not publish or trigger remote builds.

References: [registry format](https://docs.r-universe.dev/publish/set-up.html),
[reserved package names](https://docs.r-universe.dev/publish/terms.html),
[public API](https://docs.r-universe.dev/browse/api.html), and
[reproducibility limits](https://docs.r-universe.dev/install/reproducibility.html).

## Verification

Completed: the package list is unchanged; the validator, regression suite and
restricted-permission CI are added. README now distinguishes registration,
hosted builds, package availability, SDK support and scientific qualification.

- Offline registry check: six entries pass.
- Regression suite: 11 tests pass on both Apple Python 3.9.6 and Python 3.14.4,
  including malformed JSON, duplicates, private/archived upstreams, wrong package
  identity, release tags, CRLF DESCRIPTION files and operation outside a checkout.
- Explicit live check: all six repositories are public and unarchived; package
  identities match DESCRIPTION at resolved commits. No remote mutation occurs.
- R 4.6.1: all six packages appear in `available.packages()`. A source install of
  tivis.r 0.1.0 in a new isolated library loaded successfully; its RemoteSha
  `1a28d08f8a24fbeaed0e353ba81aa20f5f36831a` matches retained public API metadata.
- Workflow syntax and `git diff --check` pass. No new Python dependency is needed.

The first installation verification incorrectly expected `RemoteSha` in the
package index; that assertion failed because the index omits the field. The
installation itself succeeded. The corrected verification compares installed
DESCRIPTION with the public API; the original failure log is retained separately.

First use: `python3 scripts/validate_registry.py`,
`python3 -m unittest discover -s tests -v`, then opt in to
`python3 scripts/validate_registry.py --upstream` for live checks. README gives
the R installation commands. A network/rate-limit failure must be retried and
investigated; it does not invalidate or replace the offline result.

Next external actions: choose an explicit repository license and review/publish
the maintenance branch when authorized, then observe its hosted CI. Existing
R-universe builds were observed; the new CI has not run remotely. No registry
entry was added/removed and no push, merge or build trigger was performed.

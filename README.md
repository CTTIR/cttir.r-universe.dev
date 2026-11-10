# cttir.r-universe.dev

Package registry for the [CTTIR r-universe](https://cttir.r-universe.dev).

The November 2026 inventory covers 41 packages from 40 public CTTIR
repositories. The complete package list and source URLs are in
[`packages.json`](packages.json). `delphyr` and `delphyrApp` share the
`delphyR` repository and declare their separate package subdirectories.
`scientometricsInR` is built from the `scientometrics-in-r` repository.
Private repositories and package-shaped test fixtures are not registered.

`packages.json` lists the repositories R-universe builds. After a registry change
is merged and published, R-universe discovers it and schedules builds. An entry
alone does not guarantee that an installable package exists. Check the
[build dashboard](https://cttir.r-universe.dev/builds) before installing:

```r
install.packages("tivis.r", repos = c("https://cttir.r-universe.dev",
                                      "https://cloud.r-project.org"))
library(tivis.r)
packageDescription("tivis.r", fields = c("Version", "RemoteUrl", "RemoteSha"))
```

This also lets packages on CRAN declare optional dependencies that are not
themselves on CRAN, via `Additional_repositories:` in `DESCRIPTION` — which is
how `hyperspectR` suggests `cuvis.r` and `tivis.r`.

## Notes

The registry tracks each repository's default branch unless an explicit `branch`
is supplied. A successful build can therefore change without a version-number
change. Record `RemoteSha` for an analysis, and retain the package artifact when
long-term reproducibility is required; R-universe
[does not archive all older versions](https://docs.r-universe.dev/install/reproducibility.html).

`cuvis.r` wraps the proprietary Cubert CUVIS SDK. Stub builds can satisfy package
dependencies but cannot read `.cu3s` files; that operation needs an SDK-enabled
installation. Follow the [package instructions](https://github.com/CTTIR/cuvis.r).
`tivis.r` does not require that SDK. Package availability and build status do not
establish correctness for a particular instrument or scientific workflow.

## Maintain the registry

Prerequisites: Python 3.9 or newer and Git. No Python packages are required.

```sh
python3 scripts/validate_registry.py
python3 -m unittest discover -s tests -v
python3 scripts/validate_registry.py --upstream
python3 scripts/validate_registry.py --discover
```

The first two commands are offline and run in CI. The opt-in upstream check
reads public GitHub metadata, resolves each selected reference to a commit and
checks its DESCRIPTION identity; it does not install, build or publish packages.
GitHub rate limits or unavailable metadata cause a failed check, never a pass.
Transient HTTP 500/502/503/504 responses and interrupted connections receive at
most three attempts, with one- and two-second delays. Permission, not-found,
rate-limit and malformed-metadata failures remain terminal. Error messages report
HTTP status or connection failure without credentials or response contents.
The discovery check reads the public organization catalogue, follows pagination,
and identifies packages at repository roots and `packages/*`. It reports missing
entries without rewriting the registry. Other package locations must be reviewed
and registered explicitly. Tests, fixtures and vendored dependency trees are not
searched. A malformed or truncated response fails the check.

The full catalogue requires more requests than GitHub's unauthenticated hourly
allowance. Local checks can use an existing `GH_TOKEN` or `GITHUB_TOKEN`; keep the
token in the environment, not in a command argument, file or registry entry.
Only requests to `https://api.github.com` receive it, and redirects do not carry
it forward. CI uses its read-only repository token for live identity and discovery
checks on main pushes, manual dispatches and a daily schedule. Pull requests run
offline validation and tests. New packages need a reviewed registry change when
the discovery job reports them; no job silently adds repositories or publishes
private content.

Add only reviewed public CTTIR repositories. Package names must match DESCRIPTION
exactly and be unique. Use `subdir` for a package below the repository root;
optional `branch` and `metadata` follow the
[R-universe registry format](https://docs.r-universe.dev/publish/set-up.html).
Keep the default branch implicit unless tracking a particular branch/tag or
`*release` is intentional. This registry's validator deliberately restricts URLs
to the CTTIR GitHub organization; supporting a new host requires a policy change.

## Enable updates and verify availability

Install the official [R-universe GitHub App](https://github.com/apps/r-universe)
for CTTIR. Select this registry and the public package repositories that it lists;
private repositories are unnecessary. The app requests repository metadata read
access and commit-status write access. Confirm the current permissions on the
installation screen. Keep the selected repository list in sync when adding a
new package. See the [official setup instructions](https://docs.r-universe.dev/publish/set-up.html).

After publishing a registry change, inspect the
[generated build workflows](https://github.com/r-universe/cttir/actions) and the
[build dashboard](https://cttir.r-universe.dev/builds). Then read
[`/api/ls`](https://cttir.r-universe.dev/api/ls) and
[`/api/packages`](https://cttir.r-universe.dev/api/packages). Check each package's
`_commit.id`, `_status`, `_registered` and `_indexed` against the intended source.
An older successful artifact can remain available while a newer build is pending
or has failed. A recent API publication timestamp alone does not prove that the
latest Git commit was built.

The upstream owner's universe is eligible for global R-universe search.
Package maintainers can improve discovery with a relevant description, the
universe URL in `DESCRIPTION`, and meaningful `X-schema.org-keywords` or GitHub
topics. [Metadata guidance](https://docs.r-universe.dev/publish/metadata.html)
and [indexing rules](https://docs.r-universe.dev/browse/search.html) describe these
fields. Registry inclusion and successful builds do not constitute formal
rOpenSci software review or scientific acceptance.

Before publication, review the registry diff and upstream check. After an
authorized merge/push, verify the public API, build dashboard and installation
from a fresh library. To recover from a bad registry change, revert that reviewed
entry and verify the subsequent hosted rebuild; changing this file does not
immediately remove previously built artifacts. See [MAINTENANCE.md](MAINTENANCE.md)
for the current audit and remaining gates.

## Use of LLM tools

Where applicable, LLM tools were used for narrowly defined, non-authorial tasks:
copyediting, prose refinement, Markdown/LaTeX formatting, boilerplate scaffolding
(such as CI configurations and build scripts), and code refactoring. Tools included
[Chat AI](https://kisski.gwdg.de/leistungen/2-02-llm-service/), the KISSKI
(GWDG) service, and self-hosted **Mistral Small (24B, Apache-2.0)** served through
a local **vLLM architecture** on an Ubuntu Linux workstation with Intel
processors and NVIDIA GPUs. Self-hosted use also includes models that were
further trained (fine-tuned) or weight-edited in-house for specific tasks.
All self-hosted models ran locally, with no data sent to third parties.

All scientific claims, methodological choices, analyses, interpretations and
conclusions remain the authors' own. Where applicable, LLM-generated material
must be reviewed and revised before inclusion, and references must be verified
against their DOI, arXiv ID or ISBN.

Local software setup: vLLM with Python/PyTorch, plus R and RStudio.

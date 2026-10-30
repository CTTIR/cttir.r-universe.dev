# cttir.r-universe.dev

Package registry for the [CTTIR r-universe](https://cttir.r-universe.dev).

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
```

The first two commands are offline and run in CI. The opt-in upstream check
reads public GitHub metadata, resolves each selected reference to a commit and
checks its DESCRIPTION identity; it does not install, build or publish packages.
GitHub rate limits or unavailable metadata cause a failed check, never a pass.

Add only reviewed public CTTIR repositories. Package names must match DESCRIPTION
exactly and be unique. Use `subdir` for a package below the repository root;
optional `branch` and `metadata` follow the
[R-universe registry format](https://docs.r-universe.dev/publish/set-up.html).
Keep the default branch implicit unless tracking a particular branch/tag or
`*release` is intentional. This registry's validator deliberately restricts URLs
to the CTTIR GitHub organization; supporting a new host requires a policy change.

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
processors and NVIDIA GPUs. The self-hosted model ran locally, with no data sent
to third parties.

All scientific claims, methodological choices, analyses, interpretations and
conclusions remain the authors' own. Where applicable, LLM-generated material
must be reviewed and revised before inclusion, and references must be verified
against their DOI, arXiv ID or ISBN.

Local software setup: vLLM with Python/PyTorch, plus R and RStudio.

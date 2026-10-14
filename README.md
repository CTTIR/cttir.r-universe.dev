# cttir.r-universe.dev

Package registry for the [CTTIR r-universe](https://cttir.r-universe.dev).

`packages.json` lists the repositories r-universe builds. Adding an entry here
publishes that package to <https://cttir.r-universe.dev>, so it can be
installed with:

```r
install.packages("tivis.r", repos = c("https://cttir.r-universe.dev",
                                      "https://cloud.r-project.org"))
```

This also lets packages on CRAN declare optional dependencies that are not
themselves on CRAN, via `Additional_repositories:` in `DESCRIPTION` — which is
how `hyperspectR` suggests `cuvis.r` and `tivis.r`.

## Notes

`cuvis.r` wraps the proprietary Cubert CUVIS SDK. It builds here in stub mode,
since the SDK is not available on the build machines; that is sufficient for
dependency resolution, but reading `.cu3s` files requires the SDK locally.
`tivis.r` is pure R and fully functional as built.

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

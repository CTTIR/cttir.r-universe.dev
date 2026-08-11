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

---
eatmycode_version: "2.0.0"
---
# Reproducible kerness integration

Owner: [Review panels](../modules/harness.md)

Read when: changing `requirements.txt`, `patches/`, kerness APIs or its binding,
dependency provenance, build prerequisites, advisories or license obligations.

## Contract

Kerness is the sole top-level Python dependency. Build the public source at
`7c97dcb4e50a8fd05d05185b0052ba1356be016a` with tracked
`patches/kerness-pyo3.patch`; `requirements.txt` records installed version
`0.1.2.dev0`, not a PyPI bootstrap. An ignored `vendor/kerness/` checkout is
optional and never a runtime dependency. Required setup is Python 3.10+, Git
2.32+, Rust/Cargo and a C linker; pip uses the maturin backend with Cargo locked
dependencies. [README setup](../../README.md#setup) is the canonical build recipe.
The launcher never installs/builds packages.

The patch upgrades PyO3 0.23.5 to 0.29.2, adapts binding APIs/conversion bounds/
clone extraction, updates the lockfile and reconciles workspace package versions
for locked builds. It addresses RUSTSEC-2025-0020 and RUSTSEC-2026-0177 dependency
versions; no reachable affected API use was established here. No core review
algorithm is patched. Kerness already supplies owned runs and custom channels.
Preserve the public pin and patch together; a local-only source checkout cannot
establish reproducible installation (`patches/README.md`).

Kerness is MIT-licensed; retain upstream notices in `patches/LICENSE.kerness`
and built-wheel metadata/license. The patch's recorded OSV and upstream test
results are historical evidence, not a current assurance. Changes to pins,
dependency graph or bindings require renewed advisory/license checks and public
reproducibility. Retire the patch only when a public upstream revision supplies
a tested equivalent; update pin, setup and evidence together.

Rebuild the Rust binding after relevant upstream Python/API changes too: a stale
extension can fail importing `RunControl` before selfcheck starts. Do not treat
an installed local version as the support contract. The standard library cannot
reasonably replace the adopted orchestration/binding API within this task;
additional top-level dependencies still need project-specific justification.

## Change and Verify

Read [Panels](../modules/harness.md) for actual session/owned-run APIs and
[provider observation](provider-observation.md) when changing provider seams.
Run [root checks](../../ARCHITECTURE.md#verification), including selfcheck, from
repository root after the public pinned build. Expected selfcheck output is
`OK: all core checks passed`; the workflow suite must exit 0. Fresh installation
must work without an existing optional vendor checkout or unpublished changes.

For dependency patch development, after building `vendor/kerness/` at the public
pin plus tracked patch and installing its test prerequisites, also run from root:

```sh
.venv/bin/python -m pytest vendor/kerness/bindings/python/tests -q
cargo test --manifest-path vendor/kerness/Cargo.toml -p kerness --locked
cargo clippy --manifest-path vendor/kerness/Cargo.toml --workspace --all-targets --locked -- -D warnings
```

All must exit 0; historical test counts do not substitute for new results.
Applying the patch to pristine public source must reproduce the tested tree.
These upstream checks are optional when the dependency is unchanged and no
vendor source checkout is installed; root workflow/selfcheck remain required.

## Evidence and Gaps

[Patch provenance](../../patches/README.md) records source, license, resolved
advisory versions and dated upstream verification. Current offline tests prove
integration behavior, not live model quality or fresh advisory status. This
architecture migration changes no dependency/pin/patch; upstream dependency
patch tests are outside its scope.

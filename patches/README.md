# kerness compatibility patch

`kerness-pyo3.patch` applies to public kerness revision
`7c97dcb4e50a8fd05d05185b0052ba1356be016a`.
[kerness](https://github.com/xwings/kerness) is copyright its contributors and
distributed under the [MIT license](https://github.com/xwings/kerness/blob/7c97dcb4e50a8fd05d05185b0052ba1356be016a/LICENSE).
The built wheel includes the upstream license and metadata.
The upstream copyright and permission notice is also retained in
[LICENSE.kerness](LICENSE.kerness) alongside this patch.

The patch upgrades PyO3 0.23.5 to 0.29.2 and adapts the Rust/Python bindings to
the current APIs. It addresses dependencies affected by RUSTSEC-2025-0020 and
RUSTSEC-2026-0177. No reachable use of the affected APIs was found in this
project; the upgrade removes the vulnerable dependency versions.

Changes are limited to binding compatibility, the PyO3 manifest constraint and
Cargo's lockfile. The patch also reconciles two existing lockfile package
versions with the workspace's declared `0.1.2-dev` version, allowing a locked
build. No core review or orchestration algorithms change.

The [installation commands](../README.md#setup) check out the exact public
source and apply this patch, then install a wheel built with Cargo's `--locked`
option. The launcher does not install or build dependencies.

Verification: all 502 Python binding tests, Rust unit/integration/doc tests,
workspace clippy with warnings denied, and kerness selfcheck pass. An OSV
query of the patched lockfile's 94 registry packages on 2026-09-06 returned no
known advisories. This is dated evidence, not a promise about future reports.

Retire this patch when a public upstream revision includes a tested equivalent
upgrade. Update the pinned revision, setup procedure and validation evidence
together; do not switch installation back to the old unpatched dependency.

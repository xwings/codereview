# Per-language style reference

> Check 1's ground truth, shared by every repo. Covers the four languages this
> tool supports first-class — Python, C, C++, Rust — plus the config formats
> every project carries. A repo whose languages differ overrides the whole file
> from its own profile. Edit freely — no code changes needed.

**The overriding rule: the repository beats this file.** These are the general
conventions. Where the file being modified consistently does something else,
the file wins, and matching its neighbours is correct even when it contradicts
the table below. A convention nobody can find in the tree is not a convention
and nothing may be demanded on its authority.

## Indentation, by language

| Language | Extensions | Indent | Notes |
| -------- | ---------- | ------ | ----- |
| Python | `.py` | 4 spaces, never tabs | PEP 8. Tabs in a Python file are an error, not a preference. |
| C | `.c`, `.h` | tabs | Braces follow the surrounding file. |
| C++ | `.cpp`, `.hpp` | tabs | As for C. |
| Rust | `.rs` | 4 spaces, never tabs | rustfmt's default, and what `cargo fmt` will rewrite the file to. |
| Assembly | `.asm`, `.s` | tabs | Instruction column alignment follows the neighbouring files. |
| Shell | `.sh` | 4 spaces | Follow the scripts already in the tree. |
| YAML | `.yml`, `.yaml` | 2 spaces | Tabs are invalid YAML. |
| TOML | `.toml` | 2 spaces | |
| Markdown | `.md` | 2 spaces for nested lists | |

Mixed indentation within a single file is a finding at **major**, because it
breaks anyone whose editor is configured for the other one. A patch that uses
the wrong indent consistently in a new file is a **nit**.

## Python

- PEP 8 for naming: `snake_case` for functions and variables, `CamelCase` for
  classes, `UPPER_SNAKE` for constants, a single leading underscore for
  module-private names.
- Type hints on new public functions. Missing ones are a **nit**.
- f-strings over `%` and `.format()` in new code.
- Context managers for anything with a `close()`.
- `except Exception:` that swallows without re-raising or logging is **major**.

## C and C++

- Tabs to indent, spaces only to align within a line.
- Declare at the point of use; C89-style top-of-function declaration blocks are
  not expected unless the file does it.
- Every allocation has a matching free on every path, including error paths.
- Fixed-width types (`uint32_t`) wherever the width is part of the meaning —
  in emulation, protocol and file-format code, that is nearly always.

## Rust

- `snake_case` for functions, variables and modules, `CamelCase` for types and
  traits, `UPPER_SNAKE` for `const` and `static`. rustc's own lints already
  warn on these, so a naming finding here is a **nit** at most.
- Every `unsafe` block carries a comment stating the invariant that makes it
  sound. An `unsafe` block without one is **major**; one whose invariant does
  not actually hold is check 7's, not check 1's.
- `.unwrap()` and `.expect()` on a path that can fail at runtime are **major** —
  the same finding as a swallowed exception. In tests and in `main` they are
  fine.
- `?` rather than `match` on `Result` purely to return the error.
- Errors are types that implement `std::error::Error`, not stringified early.
  A public function returning `Result<_, String>` is a **nit** unless the crate
  already does that everywhere.

## What CI owns, and you therefore do not

Line length, import ordering, trailing whitespace, blank-line counts, and
end-of-line markers. The project's linter catches these. Flagging them here
spends the contributor's attention on something a machine already handles —
leave them alone unless the patch is grossly inconsistent with its own file.

Pure formatting diffs, and reformatting of lines the patch did not otherwise
need to touch, are worth one **info** note asking for them to be split out.
Do not file one finding per reformatted line.

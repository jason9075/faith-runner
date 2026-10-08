# Repository Guidelines

## Project Structure & Module Organization

- `src/`: Bevy application, rendering, input, settings, audio, and viewmodels.
- `crates/faith_move/`: engine-independent movement, collision, tuning, and procedural courses; depends only on `glam`.
- `crates/faith_anim/`: animation selection, body/camera placement, and sound decisions.
- `crates/me_assets/`: UE3 package, mesh, animation, texture, and sound readers.
- `tools/me-extract/`: Python extraction scripts and Ghidra helpers.

Keep Bevy integration in the application layer. Game assets come from a local Mirror's Edge installation.

## Build, Test, and Development Commands

Run from the repository root with Rust installed; recipes also require `just`.

- `just dev 1`: run a development build on the Moves map.
- `just run`: launch the release build; `just build` builds it without launching.
- `just check`: type-check all workspace targets.
- `just test-move` / `cargo test -p faith_move`: run movement regressions.
- `just test` / `cargo test --workspace`: run workspace tests.
- `just fmt`: run rustfmt; `just lint`: run Clippy across workspace targets.
- `just capture`: save scripted gameplay screenshots under `shots/`.

Use default features for routine checks; `prologue` and `retarget` reference source files absent from this checkout.

## Coding Style & Naming Conventions

Use Rust 2024, four-space indentation, `snake_case` functions/modules, `PascalCase` types, and `SCREAMING_SNAKE_CASE` constants. Use rustfmt and Clippy through the recipes above. Keep movement tuning in `crates/faith_move/src/tuning.rs`; preserve `ME:` provenance comments and mark estimates `guess`.

## Testing Guidelines

Use Rust's built-in `#[test]` harness. Tests live in each crate's `src/tests.rs`, `src/*_tests.rs`, or inline test modules. Name tests after behavior, such as `falls_and_lands`. Add deterministic scripted-input regressions for movement changes, using small worlds and fixed timesteps. No coverage threshold is configured.

Set `ME_INSTALL=/path/to/mirrors-edge` when running workspace tests to exercise install-dependent asset and animation checks; those checks return early without it.

## Commit & Pull Request Guidelines

History uses descriptive, sentence-case subjects, such as `Justfile with run, capture, test and lint recipes`. Keep commits focused. PRs should explain behavior changes, link relevant issues, report validation, and include screenshots for visual changes. Update `README.md` when controls or configuration change.

## Assets & Configuration

Use `FAITH_ME_DIR` or local `me_path.txt` for runtime asset discovery. Never commit game packages, decompiled scripts, or local installation paths.

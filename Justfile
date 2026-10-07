# List recipes
default:
    @just --list

# Run the game (release). Pass a map: `just run 1` (Moves), `just run 2` (Springboard)
run map="":
    FAITH_MAP={{map}} cargo run --release

# Run in a dev build (faster to compile, slower to play)
dev map="":
    FAITH_MAP={{map}} cargo run

# Run with the Mirror's Edge prologue map from your install
prologue:
    FAITH_MAP=prologue cargo run --release --features prologue

# Build the release binary
build:
    cargo build --release

# Movement controller tests
test-move:
    cargo test -p faith_move

# All tests; set ME_INSTALL to your Mirror's Edge folder to include the asset tests
test:
    cargo test --workspace

# Scripted capture run: saves PNGs of each move into shots/
capture dir="shots":
    FAITH_CAPTURE={{dir}} cargo run --release

# Photograph each Rooftops checkpoint
capture-tour dir="shots":
    FAITH_CAPTURE={{dir}} FAITH_CAPTURE_TOUR=1 cargo run --release

# Shoot the springboard, beam, swing, zipline and kick on the Moves map
capture-moves dir="shots":
    FAITH_CAPTURE={{dir}} FAITH_CAPTURE_MOVES=1 cargo run --release

# Format all crates
fmt:
    cargo fmt --all

# Clippy across the workspace
lint:
    cargo clippy --workspace --all-targets

# Type-check without building
check:
    cargo check --workspace --all-targets

# Remove build artifacts
clean:
    cargo clean

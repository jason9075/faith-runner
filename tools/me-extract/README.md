# Mirror's Edge extraction tools

Small Python scripts that read Mirror's Edge's own script package (`TdGame.u`): the default values of Faith's movement classes (where the `ME:` values in `crates/faith_move/src/tuning.rs` came from), and a decompiler that turns the move classes' bytecode back into readable UnrealScript (where the move logic in `controller.rs` came from).

They only read your installed copy. Nothing from the game is included in this project.

## Setup

The packages are LZO-compressed. Either decompress them with the Rust reader (no Python packages needed):

```
cargo run -p me_assets --example decompress -- "<Mirror's Edge>\TdGame\CookedPC\TdGame.u" TdGame.u
cargo run -p me_assets --example decompress -- "<Mirror's Edge>\TdGame\CookedPC\Engine.u" Engine.u
cargo run -p me_assets --example decompress -- "<Mirror's Edge>\TdGame\CookedPC\Core.u" Core.u
```

or copy the originals next to the scripts and `pip install python-lzo` (on Windows that may need the Microsoft C++ Build Tools).

## Use

With `TdGame.u` (and, for the decompiler, `Engine.u` and `Core.u`) next to the scripts:

```
python upk.py TdGame.u                          # decompress + print package summary
python defaults.py TdGame.u Default__TdMove_    # every move class's defaults
python defaults.py TdGame.u Default__TdPawn     # Faith's pawn: speeds, accel, air control
python animtree.py AT_C1P.upk                   # the first-person animation tree's blend nodes
python decompile.py TdGame.u TdMove_WallRun     # one class as UnrealScript
python decompile.py TdGame.u "TdMove*" > moves.uc  # every move class
```

The decompiled source is Mirror's Edge's code: read it from your own copy, but don't commit or share it (`*.uc` is in `.gitignore`).

## What's in there

- The package is UE3 version 536, licensee 43, stored as 55 LZO-compressed chunks. `upk.py` decompresses it and reads the name, import and export tables.
- `animtree.py` lists the blend nodes of an AnimTree package: each node's children (which animation or node), its blend times (`BlendWeight`), and speed thresholds (`Constraints`). The walking-state crossfade times and the swing/balance blends in `src/me_anim.rs` come from here.
- `decompile.py` reads each class's variables, enums and functions (signatures, locals, bytecode) and prints them as UnrealScript, with `if`/`else`, `while`, `switch` and `foreach` recovered from the jumps. Native functions and operators are named from `Core.u` and `Engine.u`. This build differs from stock UE3 in a few token layouts (a context expression `a.b` is `expr, u16 skip, u16 size, expr` with no property reference; `switch` has a u16 size; the array `AddItem`-style ops only have a closing token when their size covers one), all noted in the script. It decompiles every `TdMove*` class, `TdPawn` and `TdPlayerController` without errors.
- `defaults.py` reads the tagged property list of each `Default__` object: floats, ints, bools, names, object refs, and vectors/rotators. Other struct and array properties are listed by size only.
- Unreal units are centimetres, so divide lengths and speeds by 100 for metres. Rotators are in 65536ths of a full turn.

## Useful classes

| Class | What it holds |
|---|---|
| `TdPawn` | Run/sprint speeds (`SpeedMaxBaseVelocity`, `GroundSpeed`), `AccelRate`, `AirControl`, eye height, fall height limits, roll timing |
| `TdMove_Jump` | `BaseJumpZ`, `JumpAddXY` |
| `TdMove_WallRun`, `TdMove_WallrunJump` | Wallrun rise, speed limits, approach angles, jump-off push |
| `TdMove_WallClimb`, `TdMove_WallClimb180TurnJump` | Climb gravity/friction, added speed, 180 kick-off height and push |
| `TdMove_Grab`, `TdMove_IntoGrab`, `TdMove_GrabJump` | Hang position relative to the ledge, reach, jump off a ledge |
| `TdMove_StepUp`, `TdMove_SpeedVault` | Height bands for step-ups and vaults |
| `TdMove_Landing`, `TdMove_Coil`, `TdMove_Slide` | Hard landing / roll heights, coil lift, slide abort speed |

## Not in TdGame.u

- **Gravity.** The jump and wall-move scripts call `GetGravityZ()` to turn heights into speeds. The value lives in `TdGame\Config\DefaultGame.ini`: `[Engine.WorldInfo] DefaultGravityZ=-800`. Faith falls at about twice that (a comment under `[TdGame.TdPawn]` measures 1600 uu/s after a 780 cm fall, ≈1641 uu/s²), so that's the value used.
- **Stale config keys.** `[TdGame.TdPawn]` in that ini also sets `BaseJumpZ=560` and `AirControlAmount=0.09`, but no script property reads either any more. The jump uses `TdMove_Jump.BaseJumpZ = 630`.
- **Anything done in native C++**, such as how sprint energy builds (the script only has the tuning factors) and the exact vault/pull-up timings (animation driven). Those stay hand-tuned.

# Reading Mirror's Edge's native code with Ghidra

The UnrealScript (`decompile.py`) only has the move *rules*. Physics, sprint
acceleration and the camera live in `Binaries\MirrorsEdge.exe`. These scripts
read specific functions out of it with Ghidra's headless analyzer, without a
full auto-analysis (which takes a long time on a 31 MB exe).

Setup: Ghidra 12 with JDK 21 (`support\launch.properties`: `JAVA_HOME_OVERRIDE`).

```
analyzeHeadless <proj dir> ME -import "<ME>\Binaries\MirrorsEdge.exe" -noanalysis
analyzeHeadless <proj dir> ME -process MirrorsEdge.exe -noanalysis -scriptPath <this folder> ^
    -postScript DecompileTargets.java out.c 1 Name:hexaddr [Name:hexaddr ...]
analyzeHeadless ... -postScript DumpAsm.java out.asm Name:hexaddr ...
```

Use `name:addr`, not `name=addr`: the Windows launcher splits arguments at `=`.
The output is the game's code: keep it out of the repository.

## Finding things (the exe has no RTTI or symbols)

- **Native functions**: every script `native function` is registered in a table
  of `{ UTF-16 name, function pointer }` pairs, e.g. `intATdPawnexecGetSprintAcceleration`.
  Find the string, find the pointer to it; the next dword is the `exec` function.
- **`exec` functions are thin**: they unpack the script parameters and call the
  real method through the vtable (`call [vtable + slot]`).
- **Vtables**: each class registers with its name *without* the prefix, which the
  compiler pools into the tail of the prefixed string (`L"TdPawn"` is
  `L"ATdPawn" + 2`). The code that pushes that address passes the size and the
  `InternalConstructor`; decompile the constructor to see the vtable it stores.
  (ATdPawn: size `0x8f8`, vtable `0x1d05268`.)
- **Field offsets**: properties are laid out in declaration order, which is the
  order `defaults.py` prints them in. A run of known floats in the decompile
  pins the block, e.g. ATdPawn `+0x6b4` `SpeedMaxBaseVelocity`, `+0x6c4`
  `SpeedSprintVelocityAccelerationFactor`, `+0x6d4` `AccelCurve_LightWeapon`,
  `+0x6f4` `SpeedSprintEnergy`; AActor `+0xf4` Rotation, `+0x100` Velocity,
  `+0x68` Physics.

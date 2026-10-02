"""Dump default properties of Mirror's Edge movement classes."""
import struct
import sys

from upk import Package, R


def read_props(p, e):
    """Tagged property list of an export. Returns list of (name, index, type, value)."""
    r = R(p.data, e["off"])
    end = e["off"] + e["size"]
    r.p += 4  # NetIndex
    out = []
    while r.p < end:
        name = p.fname(r)
        if name == "None":
            break
        typ = p.fname(r)
        size, idx = r.i32(), r.i32()
        struct_name = None
        if typ == "StructProperty":
            struct_name = p.fname(r)
        if typ == "BoolProperty":
            out.append((name, idx, typ, bool(r.i32())))
            continue
        start = r.p
        if typ == "FloatProperty":
            v = r.f32()
        elif typ == "IntProperty":
            v = r.i32()
        elif typ == "ByteProperty":
            v = p.fname(r) if size == 8 else r.u8()
        elif typ == "NameProperty":
            v = p.fname(r)
        elif typ in ("ObjectProperty", "ClassProperty", "ComponentProperty", "InterfaceProperty"):
            v = p.path(r.i32())
        elif typ == "StrProperty":
            v = r.fstr()
        elif typ == "StructProperty" and struct_name in ("Vector", "Rotator") and size == 12:
            if struct_name == "Vector":
                v = (struct_name, struct.unpack_from("<3f", p.data, r.p))
            else:
                v = (struct_name, struct.unpack_from("<3i", p.data, r.p))
        else:
            v = f"<{typ}{'/' + struct_name if struct_name else ''} {size}b>"
        r.p = start + size
        out.append((name, idx, typ, v))
    return out


def main():
    p = Package(sys.argv[1] if len(sys.argv) > 1 else "TdGame.u")
    pat = sys.argv[2] if len(sys.argv) > 2 else "Default__TdMove"
    for e in p.exports:
        if e["name"].startswith(pat) or e["name"] == pat:
            print(f"== {e['name']}  (class {p.class_of(e)})")
            try:
                for name, idx, typ, v in read_props(p, e):
                    if typ in ("ObjectProperty", "ComponentProperty") and "Default__" not in str(v):
                        pass
                    ix = f"[{idx}]" if idx else ""
                    vv = f"{v:.4f}" if isinstance(v, float) else v
                    print(f"   {name}{ix} = {vv}")
            except Exception as ex:  # noqa
                print("   !! parse error", ex)


if __name__ == "__main__":
    main()

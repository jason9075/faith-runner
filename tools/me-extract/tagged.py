"""Generic UE3 tagged-property reader (nested structs/arrays) for inspection."""
import struct
from upk import R

ATOMIC = {"Vector": "<3f", "Rotator": "<3i", "Quat": "<4f", "Vector2D": "<2f", "Color": "<4B", "LinearColor": "<4f", "Guid": "<4I", "Plane": "<4f"}

def read_list(p, r, end):
    out = []
    while r.p < end:
        name = p.fname(r)
        if name == "None":
            break
        typ = p.fname(r); size, idx = r.i32(), r.i32()
        sname = p.fname(r) if typ == "StructProperty" else None
        if typ == "BoolProperty":
            out.append((name, idx, bool(r.i32()))); continue
        start = r.p
        out.append((name, idx, value(p, R(p.data, start), typ, sname, size)))
        r.p = start + size
    return out

def value(p, r, typ, sname, size, inner=None):
    if typ == "FloatProperty": return r.f32()
    if typ == "IntProperty": return r.i32()
    if typ == "ByteProperty": return p.fname(r) if size == 8 else r.u8()
    if typ == "NameProperty": return p.fname(r)
    if typ in ("ObjectProperty", "ClassProperty", "ComponentProperty"):
        i = r.i32()
        try: return p.path(i) if i else None
        except Exception: return i
    if typ == "StrProperty": return r.fstr()
    if typ == "StructProperty":
        if sname in ATOMIC and size == struct.calcsize(ATOMIC[sname]):
            return struct.unpack_from(ATOMIC[sname], p.data, r.p)
        return dict_of(read_list(p, r, r.p + size))
    if typ == "ArrayProperty":
        return ("array", size, r.p)
    return f"<{typ} {size}>"

def dict_of(lst):
    d = {}
    for n, i, v in lst:
        d[n if i == 0 else f"{n}[{i}]"] = v
    return d

def struct_array(p, at):
    """Array whose elements are tagged structs."""
    r = R(p.data, at); n = r.i32(); out = []
    for _ in range(n):
        out.append(dict_of(read_list(p, r, len(p.data))))
    return out

def obj(p, e):
    r = R(p.data, e["off"]); r.p += 4
    return dict_of(read_list(p, r, e["off"] + e["size"]))

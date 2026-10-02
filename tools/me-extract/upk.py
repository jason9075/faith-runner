"""Decompress and index a Mirror's Edge (UE3 v536, licensee 43) package.

Writes <name>.decomp (the uncompressed package body) and prints a summary.
Import as a module to get names / imports / exports.
"""
import struct
import sys

TAG = 0x9E2A83C1


class R:
    def __init__(self, b, pos=0):
        self.b, self.p = b, pos

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]; self.p += 4; return v

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]; self.p += 4; return v

    def u64(self):
        v = struct.unpack_from("<Q", self.b, self.p)[0]; self.p += 8; return v

    def u16(self):
        v = struct.unpack_from("<H", self.b, self.p)[0]; self.p += 2; return v

    def f32(self):
        v = struct.unpack_from("<f", self.b, self.p)[0]; self.p += 4; return v

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def fstr(self):
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            s = self.b[self.p:self.p + n - 1].decode("latin-1"); self.p += n; return s
        n = -n
        s = self.b[self.p:self.p + 2 * (n - 1)].decode("utf-16-le"); self.p += 2 * n; return s


def summary(raw):
    r = R(raw)
    assert r.u32() == TAG
    ver = r.u16(); lic = r.u16()
    s = dict(ver=ver, lic=lic)
    s["header_size"] = r.i32()
    s["folder"] = r.fstr()
    s["flags"] = r.u32()
    s["name_count"], s["name_off"] = r.i32(), r.i32()
    s["export_count"], s["export_off"] = r.i32(), r.i32()
    s["import_count"], s["import_off"] = r.i32(), r.i32()
    s["depends_off"] = r.i32()
    r.p += 16  # guid
    gens = r.i32()
    r.p += gens * 12
    s["engine"], s["cooker"] = r.i32(), r.i32()
    s["compression"] = r.u32()
    n = r.i32()
    s["chunks"] = [(r.i32(), r.i32(), r.i32(), r.i32()) for _ in range(n)]
    s["summary_end"] = r.p
    return s


def decompress(raw, s):
    import lzo  # only needed for compressed packages

    size = max(uo + us for uo, us, _, _ in s["chunks"])
    out = bytearray(size)
    out[: s["summary_end"]] = raw[: s["summary_end"]]
    for uo, us, co, cs in s["chunks"]:
        r = R(raw, co)
        assert r.u32() == TAG, "bad chunk tag"
        block = r.i32()
        _csum, usum = r.i32(), r.i32()
        blocks = []
        left = usum
        while left > 0:
            c, u = r.i32(), r.i32()
            blocks.append((c, u)); left -= u
        dst = uo
        for c, u in blocks:
            data = lzo.decompress(bytes(raw[r.p:r.p + c]), False, u)
            out[dst:dst + u] = data
            dst += u; r.p += c
    return bytes(out)


class Package:
    def __init__(self, path):
        raw = open(path, "rb").read()
        self.s = s = summary(raw)
        self.data = decompress(raw, s) if s["compression"] else raw
        d = self.data
        r = R(d, s["name_off"])
        self.names = []
        for _ in range(s["name_count"]):
            self.names.append(r.fstr()); r.u64()
        r = R(d, s["import_off"])
        self.imports = []
        for _ in range(s["import_count"]):
            cpkg = self.fname(r); cls = self.fname(r); outer = r.i32(); name = self.fname(r)
            self.imports.append(dict(class_pkg=cpkg, cls=cls, outer=outer, name=name))
        r = R(d, s["export_off"])
        self.exports = []
        for i in range(s["export_count"]):
            e = dict(cls=r.i32(), sup=r.i32(), outer=r.i32(), name=self.fname(r), arch=r.i32(),
                     flags=r.u64(), size=r.i32(), off=r.i32())
            if s["ver"] < 543:
                n = r.i32(); r.p += 12 * n  # component map
            e["eflags"] = r.i32()
            n = r.i32(); r.p += 4 * n       # net object counts
            r.p += 16 + 4                   # guid, package flags
            self.exports.append(e)
        self.export_end = r.p

    def fname(self, r):
        i, n = r.i32(), r.i32()
        base = self.names[i] if 0 <= i < len(self.names) else f"<bad name {i}>"
        return base if n == 0 else f"{base}_{n - 1}"

    def obj_name(self, idx):
        if idx > 0:
            return self.exports[idx - 1]["name"]
        if idx < 0:
            return self.imports[-idx - 1]["name"]
        return "None"

    def class_of(self, e):
        return self.obj_name(e["cls"]) if e["cls"] else "Class"

    def path(self, idx):
        parts = []
        while idx:
            parts.append(self.obj_name(idx))
            idx = (self.exports[idx - 1]["outer"] if idx > 0 else self.imports[-idx - 1]["outer"])
        return ".".join(reversed(parts))


if __name__ == "__main__":
    p = Package(sys.argv[1])
    s = p.s
    print({k: v for k, v in s.items() if k != "chunks"}, "chunks", len(s["chunks"]))
    print("names", len(p.names), p.names[:8])
    print("imports", len(p.imports), p.imports[:3])
    print("export table ends at", p.export_end, "depends at", s["depends_off"])
    for e in p.exports[:5]:
        print(e)
    open(sys.argv[1] + ".decomp", "wb").write(p.data)

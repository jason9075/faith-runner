"""Decode Mirror's Edge AnimSequences (AS_*.upk)."""
import struct, math
from upk import Package, R
from defaults import read_props

def _find(p, e, prop):
    r = R(p.data, e["off"]); r.p += 4
    while True:
        n = p.fname(r)
        if n == "None":
            return None, r.p
        t = p.fname(r); size, idx = r.i32(), r.i32()
        if t == "StructProperty": p.fname(r)
        if t == "BoolProperty": r.i32(); continue
        if n == prop:
            return r.p, None
        r.p += size

def _w(x, y, z):
    return math.sqrt(max(0.0, 1.0 - x*x - y*y - z*z))

def load_animset(path):
    p = Package(path)
    aset = next(e for e in p.exports if p.class_of(e) == "TdAnimSet")
    o, _ = _find(p, aset, "TrackBoneNames"); r = R(p.data, o)
    bones = [p.fname(r) for _ in range(r.i32())]
    seqs = {}
    for e in p.exports:
        if p.class_of(e) != "AnimSequence":
            continue
        d = {n: v for n, i, t, v in read_props(p, e)}
        o, _ = _find(p, e, "CompressedTrackOffsets"); r = R(p.data, o)
        offs = [r.i32() for _ in range(r.i32())]
        _, end = _find(p, e, "__none__")
        n = struct.unpack_from("<i", p.data, end)[0]
        stream = p.data[end + 4:end + 4 + n]
        tracks = []
        for k in range(0, len(offs), 4):
            to, tk, ro, rk = offs[k:k + 4]
            trans = [struct.unpack_from("<3f", stream, to + 12 * j) for j in range(tk)]
            if rk == 1:
                x, y, z = struct.unpack_from("<3f", stream, ro)
                rots = [(x, y, z, _w(x, y, z))]
            else:
                # Animated tracks: a 24-byte per-track header (unused for decoding),
                # then standard UE3 Fixed48NoW keys: x = (u - 32767) / 32767.
                rots = []
                for j in range(rk):
                    u = struct.unpack_from("<3H", stream, ro + 24 + 6 * j)
                    x, y, z = ((u[c] - 32767) / 32767.0 for c in range(3))
                    rots.append((x, y, z, _w(x, y, z)))
            tracks.append((trans, rots))
        seqs[d["SequenceName"]] = dict(length=d["SequenceLength"], frames=d["NumFrames"],
                                       rate=d.get("RateScale", 1.0), tracks=tracks)
    return bones, seqs

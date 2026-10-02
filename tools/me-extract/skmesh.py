"""Read a Mirror's Edge (UE3 v536/lic 43) SkeletalMesh: skeleton + LOD0 geometry."""
import struct
from upk import Package, R

def after_props(p, e):
    r = R(p.data, e["off"]); r.p += 4
    while True:
        n = p.fname(r)
        if n == "None":
            return r.p
        t = p.fname(r); size, idx = r.i32(), r.i32()
        if t == "StructProperty": p.fname(r)
        if t == "BoolProperty": r.i32(); continue
        r.p += size

def read_skeleton(p, e):
    r = R(p.data, after_props(p, e))
    r.i32()                                  # ME-specific leading int (=1)
    bounds = struct.unpack_from("<7f", p.data, r.p); r.p += 28
    nmat = r.i32(); mats = [r.i32() for _ in range(nmat)]
    origin = struct.unpack_from("<3f", p.data, r.p); r.p += 12
    rot = struct.unpack_from("<3i", p.data, r.p); r.p += 12
    nb = r.i32(); bones = []
    for _ in range(nb):
        name = p.fname(r); flags = r.i32()
        q = struct.unpack_from("<4f", p.data, r.p); r.p += 16
        t = struct.unpack_from("<3f", p.data, r.p); r.p += 12
        nchild = r.i32(); parent = r.i32(); color = r.i32()
        bones.append(dict(name=name, q=q, t=t, parent=parent, nchild=nchild))
    return dict(bounds=bounds, mats=mats, origin=origin, rot=rot, bones=bones, end=r.p)

def _unpack_normal(b):
    # UE3 FPackedNormal: bytes/127.5 - 1
    return tuple(x / 127.5 - 1.0 for x in b[:3])

def read_lod0(p, e):
    """Skeleton + LOD0: sections, indices, vertices with up to 4 bone weights."""
    s = read_skeleton(p, e)
    d = p.data
    o = s["end"]
    s["depth"] = struct.unpack_from("<i", d, o)[0]; o += 4
    nlod = struct.unpack_from("<i", d, o)[0]; o += 4
    nsec = struct.unpack_from("<i", d, o)[0]; o += 4
    secs = []
    for _ in range(nsec):
        mat, chunk = struct.unpack_from("<HH", d, o)
        base = struct.unpack_from("<I", d, o + 4)[0]
        ntri = struct.unpack_from("<H", d, o + 8)[0]
        secs.append(dict(mat=mat, chunk=chunk, base=base, ntri=ntri)); o += 10
    esz, nidx = struct.unpack_from("<ii", d, o); o += 8
    idx = list(struct.unpack_from(f"<{nidx}H", d, o)); o += esz * nidx
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + 2 * n          # shadow indices
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + 2 * n          # active bones
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n              # shadow double-sided
    nch = struct.unpack_from("<i", d, o)[0]; o += 4
    verts = []
    chunks = []
    for _ in range(nch):
        base = struct.unpack_from("<i", d, o)[0]; o += 4
        rig = []
        nr = struct.unpack_from("<i", d, o)[0]; o += 4
        for k in range(nr):
            v = o + 49 * k
            rig.append(dict(pos=struct.unpack_from("<3f", d, v),
                            nrm=_unpack_normal(d[v + 20:v + 24]),
                            uv=struct.unpack_from("<2f", d, v + 24),
                            bones=(d[v + 48],), weights=(255,)))
        o += 49 * nr
        soft = []
        ns = struct.unpack_from("<i", d, o)[0]; o += 4
        for k in range(ns):
            v = o + 56 * k
            soft.append(dict(pos=struct.unpack_from("<3f", d, v),
                             nrm=_unpack_normal(d[v + 20:v + 24]),
                             uv=struct.unpack_from("<2f", d, v + 24),
                             bones=tuple(d[v + 48:v + 52]), weights=tuple(d[v + 52:v + 56])))
        o += 56 * ns
        nbm = struct.unpack_from("<i", d, o)[0]; o += 4
        bonemap = list(struct.unpack_from(f"<{nbm}H", d, o)); o += 2 * nbm
        numrig, numsoft, maxinf = struct.unpack_from("<3i", d, o); o += 12
        for v in rig + soft:
            v["bones"] = tuple(bonemap[b] for b in v["bones"])
        chunks.append(dict(base=base, nrig=nr, nsoft=ns, bonemap=bonemap, maxinf=maxinf))
        verts += rig + soft
    s.update(sections=secs, indices=idx, verts=verts, chunks=chunks, lod_end=o)
    return s

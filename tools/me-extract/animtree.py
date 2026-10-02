"""Dump an AnimTree's blend nodes (children, blend times, speed constraints).

Usage: python animtree.py AT_C1P.upk [NodeClass ...]
"""
import struct, sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upk import Package, R

def props_raw(p, e):
    r = R(p.data, e["off"]); end = e["off"] + e["size"]; r.p += 4
    out = []
    while r.p < end:
        name = p.fname(r)
        if name == "None": break
        typ = p.fname(r); size, idx = r.i32(), r.i32()
        sn = p.fname(r) if typ == "StructProperty" else None
        if typ == "BoolProperty":
            out.append((name, typ, r.i32())); continue
        start = r.p
        out.append((name, typ, p.data[start:start+size], sn))
        r.p = start + size
    return out

def children(p, raw):
    # array of AnimBlendChild structs: Name(NameProperty), Anim(ObjectProperty), Weight...
    r = R(raw, 0); n = r.i32(); res = []
    for _ in range(n):
        d = {}
        while True:
            name = p.fname(r)
            if name == "None": break
            typ = p.fname(r); size, idx = r.i32(), r.i32()
            if typ == "StructProperty": p.fname(r)
            if typ == "BoolProperty": d[name] = r.i32(); continue
            st = r.p
            if typ == "NameProperty": d[name] = p.fname(r)
            elif typ == "ObjectProperty": d[name] = p.path(r.i32())
            elif typ == "FloatProperty": d[name] = r.f32()
            elif typ == "IntProperty": d[name] = r.i32()
            r.p = st + size
        res.append(d)
    return res

p = Package(sys.argv[1] if len(sys.argv) > 1 else 'AT_C1P.upk')
want = sys.argv[2:] or ['TdAnimNodeBlendBySpeed','TdAnimNodeMovementState','TdAnimNodeWalkingState','TdAnimNodeBalanceWalk','TdAnimNodeSwing','TdAnimNodeBlendDirectional','TdAnimNodeLandOffset','TdAnimNodeTurn','TdAnimNodeAimOffset']
for e in p.exports:
    cls = p.class_of(e)
    if cls not in want: continue
    print('==', e['name'], cls)
    for t in props_raw(p, e):
        name, typ = t[0], t[1]
        if typ == 'ArrayProperty':
            raw = t[2]
            if name == 'Children':
                for ch in children(p, raw):
                    print('    child', ch.get('Name'), '->', ch.get('Anim'))
            else:
                n = struct.unpack_from('<i', raw)[0]
                body = raw[4:]
                if len(body) == 4*n:
                    print('   ', name, [round(x,3) for x in struct.unpack_from(f'<{n}f', body)])
                else:
                    print('   ', name, n, len(body))
        elif typ == 'FloatProperty':
            print('   ', name, round(struct.unpack_from('<f', t[2])[0],3))
        elif typ in ('IntProperty',):
            print('   ', name, struct.unpack_from('<i', t[2])[0])
        elif typ == 'BoolProperty':
            print('   ', name, t[2])

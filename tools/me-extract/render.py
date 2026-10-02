import numpy as np
from pose import q2m, conj

def slerp(a, b, t):
    a = np.array(a); b = np.array(b)
    if np.dot(a, b) < 0: b = -b
    q = a * (1 - t) + b * t
    return q / np.linalg.norm(q)

def sample(seq, time):
    n = seq["frames"]; L = seq["length"]
    f = (time % L) / L * n if n > 1 else 0
    out = []
    for trans, rots in seq["tracks"]:
        def pick(keys, is_rot):
            if len(keys) == 1: return np.array(keys[0])
            i0 = int(f) % len(keys); i1 = (i0 + 1) % len(keys); a = f - int(f)
            return slerp(keys[i0], keys[i1], a) if is_rot else np.array(keys[i0]) * (1 - a) + np.array(keys[i1]) * a
        out.append((pick(rots, True), pick(trans, False)))
    return out

def world(bones, locals_, conj_anim):
    G = []
    for i, b in enumerate(bones):
        q, t = locals_[i]
        if conj_anim and i > 0: q = conj(q)
        M = np.eye(4); M[:3, :3] = q2m(q); M[:3, 3] = t
        G.append(M if i == 0 else G[b["parent"]] @ M)
    return G

def skin(mesh, G):
    bones = mesh["bones"]
    Gref = world(bones, [(b["q"], b["t"]) for b in bones], False)
    inv = [np.linalg.inv(g) for g in Gref]
    S = [G[i] @ inv[i] for i in range(len(bones))]
    out = np.zeros((len(mesh["verts"]), 3))
    for k, v in enumerate(mesh["verts"]):
        p = np.array([*v["pos"], 1.0]); acc = np.zeros(4)
        for b, w in zip(v["bones"], v["weights"]):
            if w: acc += (w / 255.0) * (S[b] @ p)
        out[k] = acc[:3]
    return out

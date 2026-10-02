"""Decompile UnrealScript bytecode from Mirror's Edge's TdGame.u back to readable source.

    python decompile.py TdGame.u TdMove_Jump [TdMove_WallRun ...]
    python decompile.py TdGame.u 'TdMove*'          # every class matching a glob

Prints, per class: its variables, every function (signature, locals, body) grouped by state.
Native function and operator names are resolved from Core.u and Engine.u, which it looks for
next to the given package. All three can be decompressed packages (see README), so python-lzo
is only needed for the originals.

Layout notes (UE3 v536, licensee 43), all offsets inside an export's data:
  every object:  NetIndex i32, tagged properties up to "None"
  UField:        SuperField, Next
  UStruct:       ScriptText, Children, CppText, Line i32, TextPos i32, ScriptSize i32, bytecode
  UFunction:     iNative u16, OperPrecedence u8, FunctionFlags u32, [RepOffset u16], FriendlyName
  UProperty:     ArrayDim i32, PropertyFlags u64, Category FName, ArraySizeEnum, [RepOffset u16]
Object references in bytecode are 4 bytes and names 8, the same as in memory on 32-bit, so
jump targets are plain offsets into the serialized script.
"""
import fnmatch
import os
import struct
import sys

from upk import Package, R

# FunctionFlags
F_FINAL, F_DEFINED, F_ITERATOR, F_LATENT, F_PREOP, F_SINGULAR, F_NET = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40
F_SIMULATED, F_EXEC, F_NATIVE, F_EVENT, F_OPERATOR, F_STATIC = 0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000
F_CONST, F_PRIVATE, F_PROTECTED, F_DELEGATE = 0x8000, 0x40000, 0x80000, 0x100000
# PropertyFlags
P_OPTIONAL, P_NET, P_PARM, P_OUT, P_RETURN, P_COERCE, P_CONST = 0x10, 0x20, 0x80, 0x100, 0x400, 0x800, 0x2

CASTS = {  # UE3 ECastToken -> target type
    0x36: "bool", 0x39: "vector", 0x3A: "int", 0x3B: "bool", 0x3C: "float", 0x3D: "byte", 0x3E: "bool",
    0x3F: "float", 0x40: "byte", 0x41: "int", 0x42: "float", 0x43: "byte", 0x44: "int", 0x45: "bool",
    0x46: "interface", 0x47: "bool", 0x48: "bool", 0x49: "byte", 0x4A: "int", 0x4B: "bool", 0x4C: "float",
    0x4D: "vector", 0x4E: "rotator", 0x4F: "bool", 0x50: "rotator", 0x51: "bool", 0x52: "string",
    0x53: "string", 0x54: "string", 0x55: "string", 0x56: "string", 0x57: "string", 0x58: "string",
    0x59: "string", 0x5A: "string", 0x60: "name",
}
# Operator precedence for parenthesising (lower binds looser); unknown operators get full parens.
PREC = {"||": 1, "^^": 2, "&&": 3, "==": 4, "!=": 4, "~=": 4, "<": 5, ">": 5, "<=": 5, ">=": 5,
        "$": 6, "@": 6, "$=": 6, "@=": 6, "+": 7, "-": 7, "*": 8, "/": 8, "%": 8, "Dot": 8, "Cross": 8,
        "ClockwiseFrom": 8, "<<": 6, ">>": 6, ">>>": 6, "&": 4, "|": 2, "^": 3, "**": 9}
ASSIGN_OPS = {"+=", "-=", "*=", "/=", "$=", "@=", "|=", "&="}


class Decompiler:
    def __init__(self, path):
        self.p = Package(path)
        self.dir = os.path.dirname(os.path.abspath(path))
        self.natives = {}
        for lib in ("Core.u", "Engine.u"):
            lp = os.path.join(self.dir, lib)
            if os.path.exists(lp) and os.path.abspath(lp) != os.path.abspath(path):
                self._index_natives(Package(lp))
            elif not os.path.exists(lp):
                print(f"// note: {lib} not found next to {path}; native calls show as native_N", file=sys.stderr)
        self._index_natives(self.p)
        self.by_path = {self.p.path(k + 1): k + 1 for k in range(len(self.p.exports))}

    # ---------- package structure ----------

    def raw(self, p, i):
        e = p.exports[i - 1]
        return p.data[e["off"]:e["off"] + e["size"]]

    def ustruct(self, p, i):
        """(super_field, next, children, script_bytes, tail_offset) of a UStruct export."""
        e = p.exports[i - 1]
        r = R(p.data, e["off"])
        r.i32()  # NetIndex
        while p.fname(r) != "None":  # no tagged props on code objects, but be safe
            raise ValueError("unexpected tagged properties on struct")
        sup, nxt = r.i32(), r.i32()
        r.i32()  # ScriptText
        children = r.i32()
        r.i32(); r.i32(); r.i32()  # CppText, Line, TextPos
        size = r.i32()
        script = p.data[r.p:r.p + size]
        return sup, nxt, children, script, r.p + size

    def function_tail(self, p, i):
        _, _, _, _, at = self.ustruct(p, i)
        r = R(p.data, at)
        inative, prec, flags = r.u16(), r.u8(), r.u32()
        if flags & F_NET:
            r.u16()
        friendly = p.fname(r)
        return inative, prec, flags, friendly

    def prop(self, p, i):
        """(name, flags, type string, next) of a UProperty export."""
        e = p.exports[i - 1]
        r = R(p.data, e["off"])
        r.i32(); p.fname(r)
        r.i32()
        nxt = r.i32()
        dim = r.i32()
        flags = r.u64()
        p.fname(r)  # category
        r.i32()  # ArraySizeEnum
        if flags & P_NET:
            r.u16()
        cls = p.class_of(e)
        simple = {"FloatProperty": "float", "IntProperty": "int", "BoolProperty": "bool", "NameProperty": "name",
                  "StrProperty": "string"}
        if cls in simple:
            t = simple[cls]
        elif cls == "ByteProperty":
            en = r.i32()
            t = p.obj_name(en) if en else "byte"
        elif cls in ("ObjectProperty", "ComponentProperty", "StructProperty", "InterfaceProperty"):
            t = p.obj_name(r.i32())
        elif cls == "ClassProperty":
            r.i32(); t = f"class<{p.obj_name(r.i32())}>"
        elif cls == "ArrayProperty":
            inner = r.i32()
            t = f"array<{self.prop(p, inner)[2] if inner > 0 else p.obj_name(inner)}>"
        elif cls == "DelegateProperty":
            t = f"delegate<{p.obj_name(r.i32())}>"
        else:
            t = cls
        if dim > 1:
            t += f"[{dim}]"
        return e["name"], flags, t, nxt

    def _index_natives(self, p):
        for k, e in enumerate(p.exports):
            if p.class_of(e) != "Function":
                continue
            try:
                inative, prec, flags, friendly = self.function_tail(p, k + 1)
            except Exception:
                continue
            if inative:
                self.natives[inative] = (friendly, flags, e["name"])

    # ---------- bytecode -> expression tree ----------

    def decode(self, script):
        """List of (offset, statement) for one function's bytecode."""
        self.s, self.o = script, 0
        out = []
        while self.o < len(script):
            at = self.o
            st = self.stmt()
            out.append((at, st))
            if st[0] == "end":
                break
        if self.o != len(script):
            raise ValueError(f"decode stopped at {self.o} of {len(script)}")
        return out

    def u8(self):
        v = self.s[self.o]; self.o += 1; return v

    def u16(self):
        v = struct.unpack_from("<H", self.s, self.o)[0]; self.o += 2; return v

    def i32(self):
        v = struct.unpack_from("<i", self.s, self.o)[0]; self.o += 4; return v

    def f32(self):
        v = struct.unpack_from("<f", self.s, self.o)[0]; self.o += 4; return v

    def obj(self):
        return self.p.obj_name(self.i32())

    def name(self):
        i, n = struct.unpack_from("<ii", self.s, self.o); self.o += 8
        base = self.p.names[i] if 0 <= i < len(self.p.names) else f"?{i}"
        return base if n == 0 else f"{base}_{n - 1}"

    def stmt(self):
        t = self.s[self.o]
        if t == 0x04:
            self.o += 1; e = self.expr(); return ("return", e)
        if t == 0x06:
            self.o += 1; return ("jump", self.u16())
        if t == 0x07:
            self.o += 1; target = self.u16(); return ("jumpifnot", target, self.expr())
        if t == 0x05:
            self.o += 1; self.u16(); return ("switch", self.expr())  # u16 size in this build
        if t == 0x0A:
            self.o += 1; nxt = self.u16()
            return ("case", nxt, None if nxt == 0xFFFF else self.expr())
        if t == 0x08:
            self.o += 1; return ("expr", "stop")
        if t == 0x09:
            self.o += 1; self.u16(); self.u8(); return ("expr", f"assert({self.expr()})")
        if t == 0x0C:
            self.o += 1; labels = []
            while True:
                n = self.name(); off = struct.unpack_from("<I", self.s, self.o)[0]; self.o += 4
                if n == "None":
                    break
                labels.append((n, off))
            return ("labels", labels)
        if t == 0x0D:
            self.o += 1; return ("expr", f"goto {self.expr()}")
        if t == 0x2F:
            self.o += 1; e = self.expr(); end = self.u16(); return ("foreach", e, end)
        if t == 0x58:  # foreach Array(Item, Index)
            self.o += 1; arr = self.expr(); item = self.expr(); has_index = self.u8(); index = self.expr()
            end = self.u16()
            return ("foreach", f"{atom(arr)}({flat(item)}{', ' + flat(index) if has_index else ''})", end)
        if t == 0x30:
            self.o += 1; return ("iterpop",)
        if t == 0x31:
            self.o += 1; return ("iternext",)
        if t == 0x53:
            self.o += 1; return ("end",)
        if t == 0x41:  # DebugInfo
            self.o += 1; self.i32(); self.i32(); self.i32(); self.u8(); return ("nop",)
        if t == 0x0B:
            self.o += 1; return ("nop",)
        return ("expr", self.expr())

    def args(self):
        out = []
        while self.s[self.o] != 0x16:
            if self.s[self.o] == 0x4A:  # EmptyParmValue: skipped optional argument
                self.o += 1; out.append(""); continue
            out.append(self.expr())
        self.o += 1
        while out and out[-1] == "":
            out.pop()
        return out

    def expr(self):
        t = self.u8()
        if t in (0x00, 0x01, 0x48, 0x29, 0x03):
            return self.obj()
        if t == 0x02:
            return f"default.{self.obj()}"
        if t == 0x0F or t == 0x14 or t == 0x44:
            a = self.expr(); b = self.expr(); return ("let", a, b)
        if t == 0x10 or t == 0x1A:
            i = self.expr(); a = self.expr(); return f"{atom(a)}[{flat(i)}]"
        if t == 0x11:
            outer, nm, flags, cls = self.expr(), self.expr(), self.expr(), self.expr()
            tmpl = self.expr()  # UE3 adds an archetype/template argument
            a = ", ".join(flat(x) for x in (outer, nm, flags) if x != "")
            return f"new{f'({a})' if a else ''} {flat(cls)}" + (f"({flat(tmpl)})" if tmpl else "")
        if t in (0x12, 0x19):
            left = self.expr(); self.u16(); self.u16(); right = self.expr()  # skip, result size
            sep = ".static." if t == 0x12 else "."
            return f"{atom(left)}{sep}{flat(right)}"
        if t == 0x13:
            c = self.obj(); return f"class<{c}>({flat(self.expr())})"
        if t == 0x17:
            return "self"
        if t == 0x18:
            self.u16(); return self.expr()
        if t == 0x1B:
            n = self.name(); return self.call(n, self.args())
        if t == 0x1C:
            i = self.i32(); return self.final_call(i, self.args())
        if t == 0x37:
            n = self.name(); return self.call("global." + n, self.args())
        if t == 0x1D:
            return str(self.i32())
        if t == 0x1E:
            return fmt_f(self.f32())
        if t == 0x1F:
            end = self.s.index(b"\0", self.o); v = self.s[self.o:end].decode("latin-1"); self.o = end + 1
            return '"' + v.replace('"', '\\"') + '"'
        if t == 0x34:
            n = 0
            while self.s[self.o + n:self.o + n + 2] != b"\0\0":
                n += 2
            v = self.s[self.o:self.o + n].decode("utf-16-le"); self.o += n + 2
            return '"' + v + '"'
        if t == 0x20:
            i = self.i32()
            return f"{self.p.class_of(self.p.exports[i - 1]) if i > 0 else self.p.imports[-i - 1]['cls']}'{self.p.obj_name(i)}'"
        if t == 0x21:
            return f"'{self.name()}'"
        if t == 0x22:
            return "rot({}, {}, {})".format(self.i32(), self.i32(), self.i32())
        if t == 0x23:
            return "vect({}, {}, {})".format(fmt_f(self.f32()), fmt_f(self.f32()), fmt_f(self.f32()))
        if t == 0x24 or t == 0x2C:
            return str(self.u8())
        if t == 0x25:
            return "0"
        if t == 0x26:
            return "1"
        if t == 0x27:
            return "true"
        if t == 0x28:
            return "false"
        if t == 0x2A:
            return "none"
        if t == 0x0B or t == 0x4A:  # Nothing, EmptyParmValue
            return ""
        if t == 0x2D:
            return self.expr()
        if t in (0x2E, 0x52):
            c = self.obj(); return f"{c}({flat(self.expr())})"
        if t == 0x51:
            return self.expr()
        if t in (0x32, 0x33):
            self.i32(); a, b = self.expr(), self.expr()
            return ("op", "==" if t == 0x32 else "!=", a, b)
        if t == 0x35:
            field = self.obj(); self.i32(); self.u8(); self.u8(); base = self.expr()
            return f"{atom(base)}.{field}"
        if t == 0x36:
            return f"{atom(self.expr())}.Length"
        if t == 0x38:
            c = self.u8(); e = self.expr()
            return f"{CASTS.get(c, f'cast{c:02x}')}({flat(e)})"
        if t in (0x39, 0x40):
            a, i, n = self.expr(), self.expr(), self.expr()
            if self.s[self.o] == 0x16:
                self.o += 1
            return f"{atom(a)}.{'Insert' if t == 0x39 else 'Remove'}({flat(i)}, {flat(n)})"
        if t == 0x3A:
            self.i32(); return ""
        if t in (0x3B, 0x3C, 0x3D, 0x3E):
            a, b = self.expr(), self.expr()
            if self.s[self.o] == 0x16:
                self.o += 1
            return ("op", "==" if t in (0x3B, 0x3D) else "!=", a, b)
        if t == 0x3F:
            return "none"
        if t == 0x42:
            self.u8(); self.i32(); n = self.name(); return self.call(n, self.args())
        if t == 0x43:  # delegate property: just its name in this build
            return self.name()
        if t == 0x4B:
            return self.name()
        if t == 0x45:
            c = self.expr(); self.u16(); a = self.expr(); self.u16(); b = self.expr()
            return f"({flat(c)} ? {flat(a)} : {flat(b)})"
        if t in (0x46, 0x47, 0x54, 0x55, 0x56, 0x57):
            # array.Op(args): array expr, u16 size of the args, the args, and an EndFunctionParms
            # only when that size covers one.
            a = self.expr(); skip = self.u16(); end = self.o + skip
            args = [self.expr()]
            while self.o < end and self.s[self.o] != 0x16:
                args.append(self.expr())
            if self.o < end and self.s[self.o] == 0x16:
                self.o += 1
            fn = {0x46: "Find", 0x47: "Find", 0x54: "Add", 0x55: "AddItem", 0x56: "RemoveItem",
                  0x57: "InsertItem"}[t]
            return f"{atom(a)}.{fn}({', '.join(flat(x) for x in args)})"
        if t == 0x49:
            self.u16(); e = self.expr(); self.o += 1; return e
        if t == 0x0E:
            self.i32(); return self.expr()
        if 0x60 <= t <= 0x6F:
            idx = ((t - 0x60) << 8) | self.u8()
            return self.native(idx)
        if t >= 0x70:
            return self.native(t)
        raise ValueError(f"unknown token 0x{t:02x} at {self.o - 1}")

    def native(self, idx):
        friendly, flags, name = self.natives.get(idx, (f"native_{idx}", 0, f"native_{idx}"))
        a = self.args()
        if flags & F_OPERATOR:
            if len(a) == 2:
                return ("op", friendly, a[0], a[1])
            if len(a) == 1:
                return ("pre" if flags & F_PREOP else "post", friendly, a[0])
        return self.call(friendly, a)

    def final_call(self, i, a):
        n = self.p.obj_name(i)
        # A final call to a function of a parent class from an override reads as super.F().
        if i and getattr(self, "cur_func", None) and n == self.cur_name and i != self.cur_func:
            owner = self.p.path(i).split(".")[0]
            return self.call(f"super({owner}).{n}" if owner else f"super.{n}", a)
        return self.call(n, a)

    def call(self, n, a):
        return f"{n}({', '.join(flat(x) for x in a)})"

    # ---------- structuring ----------

    def render(self, stmts, indent=1):
        self.stmts = stmts
        self.index = {off: k for k, (off, _) in enumerate(stmts)}
        self.lines = []
        self.labels = set()
        # The compiler ends every function with an implicit 'return;' (or ReturnNothing).
        n = len(stmts)
        while n and stmts[n - 1][1][0] in ("end", "nop"):
            n -= 1
        if n and stmts[n - 1][1][0] == "return" and flat(stmts[n - 1][1][1]) == "":
            # Keep its offset: loops and ifs that end the function jump to it.
            stmts = stmts[:n - 1] + [(stmts[n - 1][0], ("nop",))] + stmts[n:]
            self.stmts = stmts
        self.block(0, len(stmts), indent, loop=None)
        return self.lines

    def emit(self, d, text):
        self.lines.append("    " * d + text)

    def k_of(self, off):
        return self.index.get(off, len(self.stmts))

    def block(self, i, j, d, loop):
        st = self.stmts
        while i < j:
            off, s = st[i]
            kind = s[0]
            if kind == "jumpifnot":
                target = self.k_of(s[1])
                cond = flat(negate(s[2]))
                prev = st[target - 1][1] if target - 1 > i else None
                if prev and prev[0] == "jump" and prev[1] == off:  # while loop
                    self.emit(d, f"while ({flat(s[2])})")
                    self.emit(d, "{")
                    self.block(i + 1, target - 1, d + 1, loop=(off, s[1]))
                    self.emit(d, "}")
                    i = target
                    continue
                if prev and prev[0] == "jump" and prev[1] > st[target][0] if target < len(st) else False:
                    end = self.k_of(prev[1])
                    if end <= j and not (loop and prev[1] == loop[1]):
                        self.emit(d, f"if ({flat(s[2])})")
                        self.emit(d, "{")
                        self.block(i + 1, target - 1, d + 1, loop)
                        self.emit(d, "}")
                        self.emit(d, "else")
                        self.emit(d, "{")
                        self.block(target, end, d + 1, loop)
                        self.emit(d, "}")
                        i = end
                        continue
                self.emit(d, f"if ({flat(s[2])})")
                self.emit(d, "{")
                self.block(i + 1, min(target, j), d + 1, loop)
                self.emit(d, "}")
                i = min(target, j)
                continue
            if kind == "jump":
                if self.k_of(s[1]) == i + 1:  # to the next statement (empty else, trailing continue)
                    pass
                elif loop and s[1] == loop[1]:
                    self.emit(d, "break;")
                elif loop and s[1] == loop[0]:
                    self.emit(d, "continue;")
                elif getattr(self, "switch_end", None) is not None and s[1] == self.switch_end:
                    self.emit(d, "break;")
                else:
                    self.emit(d, f"goto L{s[1]};"); self.labels.add(s[1])
                i += 1
                continue
            if kind == "switch":
                i = self.switch(i, j, d, loop)
                continue
            if kind == "foreach":
                end = self.k_of(s[2])
                self.emit(d, f"foreach {flat(s[1])}")
                self.emit(d, "{")
                body_end = end - 1 if end - 1 > i and st[end - 1][1][0] == "iternext" else end
                self.block(i + 1, body_end, d + 1, loop=(off, s[2]))
                self.emit(d, "}")
                i = end
                continue
            self.simple(d, s)
            i += 1

    def switch(self, i, j, d, loop):
        st = self.stmts
        self.emit(d, f"switch ({flat(st[i][1][1])})")
        self.emit(d, "{")
        i += 1
        # The end of the switch is where its 'break' jumps go: the forward jump that ends a
        # case body. With no breaks and no default, the last case's 'next' is the end.
        end_off = None
        k = i
        while k < j and st[k][1][0] == "case":
            nxt = st[k][1][1]
            if nxt == 0xFFFF:
                break
            stop = self.k_of(nxt)
            last = st[stop - 1][1] if stop - 1 > k else None
            if last and last[0] == "jump" and last[1] > st[stop - 1][0]:
                end_off = last[1] if end_off is None else min(end_off, last[1])
            k = stop
        if end_off is None and k < j and st[k][1][0] != "case":
            end_off = st[k][0]
        saved = getattr(self, "switch_end", None)
        self.switch_end = end_off
        end_k = self.k_of(end_off) if end_off is not None else j
        while i < min(end_k, j) and st[i][1][0] == "case":
            nxt, val = st[i][1][1], st[i][1][2]
            self.emit(d + 1, "default:" if nxt == 0xFFFF else f"case {flat(val)}:")
            stop = min(self.k_of(nxt), end_k) if nxt != 0xFFFF else end_k
            self.block(i + 1, stop, d + 2, loop)
            i = stop
        self.switch_end = saved
        self.emit(d, "}")
        return max(i, end_k) if end_off is not None else i

    def simple(self, d, s):
        kind = s[0]
        if kind == "return":
            v = flat(s[1])
            self.emit(d, f"return {v};" if v else "return;")
        elif kind == "expr":
            v = flat(s[1])
            if v:
                self.emit(d, v + ";")
        elif kind == "case":
            self.emit(d, f"case {flat(s[2])}:")
        elif kind == "labels":
            for n, off in s[1]:
                self.emit(d, f"// label {n} @ {off}")
        elif kind in ("end", "nop", "iterpop", "iternext"):
            pass
        else:
            self.emit(d, f"// {s}")

    # ---------- whole classes ----------

    def signature(self, fi):
        _, _, children, _, _ = self.ustruct(self.p, fi)
        inative, prec, flags, friendly = self.function_tail(self.p, fi)
        params, locals_, ret = [], [], None
        i = children
        while i > 0:
            n, pf, t, nxt = self.prop(self.p, i)
            if pf & P_RETURN:
                ret = t
            elif pf & P_PARM:
                mods = ("optional " if pf & P_OPTIONAL else "") + ("out " if pf & P_OUT else "") + \
                       ("coerce " if pf & P_COERCE else "")
                params.append(f"{mods}{t} {n}")
            else:
                locals_.append((t, n))
            i = nxt
        words = []
        for bit, w in ((F_PRIVATE, "private"), (F_PROTECTED, "protected"), (F_STATIC, "static"),
                       (F_FINAL, "final"), (F_SIMULATED, "simulated"), (F_SINGULAR, "singular"),
                       (F_NATIVE, f"native({inative})" if inative else "native"), (F_EXEC, "exec"),
                       (F_LATENT, "latent"), (F_ITERATOR, "iterator")):
            if flags & bit:
                words.append(w)
        kw = "event" if flags & F_EVENT else ("delegate" if flags & F_DELEGATE else "function")
        words.append(kw)
        if ret:
            words.append(ret)
        tail = " const" if flags & F_CONST else ""
        return f"{' '.join(words)} {self.p.exports[fi - 1]['name']}({', '.join(params)}){tail}", locals_, flags

    def function(self, fi, d=1):
        sig, locals_, flags = self.signature(fi)
        out = ["    " * (d - 1) + sig]
        if flags & F_NATIVE and not flags & F_DEFINED:
            out[-1] += ";"
            return out
        _, _, _, script, _ = self.ustruct(self.p, fi)
        self.cur_func, self.cur_name = fi, self.p.exports[fi - 1]["name"]
        out.append("    " * (d - 1) + "{")
        for t, n in locals_:
            out.append("    " * d + f"local {t} {n};")
        try:
            body = self.render(self.decode(script), d)
            if self.labels:  # gotos the structurer couldn't express: list where they land
                body.append("    " * d + "// goto targets: " + ", ".join(f"L{x}" for x in sorted(self.labels)))
            out += body
        except Exception as ex:  # keep going: show where it broke
            out.append("    " * d + f"// !! decompile error: {ex}")
        out.append("    " * (d - 1) + "}")
        return out

    def klass(self, name):
        ci = self.by_path.get(name)
        if not ci:
            return [f"// no class {name}"]
        e = self.p.exports[ci - 1]
        sup = self.p.obj_name(e["sup"]) if e["sup"] else ""
        out = [f"class {name}" + (f" extends {sup}" if sup else "") + ";", ""]
        members = [k + 1 for k, x in enumerate(self.p.exports) if x["outer"] == ci]
        for k in members:
            x = self.p.exports[k - 1]
            if self.p.class_of(x).endswith("Property"):
                n, pf, t, _ = self.prop(self.p, k)
                out.append(f"var {t} {n};")
        for k in members:
            x = self.p.exports[k - 1]
            c = self.p.class_of(x)
            if c == "Const":
                r = R(self.p.data, x["off"]); r.i32(); self.p.fname(r); r.i32(); r.i32()
                out.append(f"const {x['name']} = {r.fstr()};")
            elif c == "Enum":
                r = R(self.p.data, x["off"]); r.i32(); self.p.fname(r); r.i32(); r.i32()
                n = r.i32(); vals = [self.p.fname(r) for _ in range(n)]
                out.append(f"enum {x['name']} {{ {', '.join(vals)} }};")
        out.append("")
        for k in members:
            x = self.p.exports[k - 1]
            c = self.p.class_of(x)
            if c == "Function":
                out += self.function(k)
                out.append("")
            elif c == "State":
                out.append(f"state {x['name']}")
                out.append("{")
                for kk in (m + 1 for m, y in enumerate(self.p.exports) if y["outer"] == k):
                    if self.p.class_of(self.p.exports[kk - 1]) == "Function":
                        out += self.function(kk, 2)
                        out.append("")
                _, _, _, script, _ = self.ustruct(self.p, k)
                if len(script) > 1:
                    self.cur_func = None
                    try:
                        out += self.render(self.decode(script), 1)
                    except Exception as ex:
                        out.append(f"    // !! state code: {ex}")
                out.append("}")
                out.append("")
        return out


# ---------- expression printing ----------

def fmt_f(v):
    s = f"{v:.6g}"
    return s if any(c in s for c in ".en") else s + ".0"


def atom(e):
    s = flat(e)
    if isinstance(e, tuple) and e[0] in ("op", "let"):
        return f"({s})"
    return s


def negate(e):
    if isinstance(e, tuple) and e[0] == "pre" and e[1] == "!":
        return e[2]
    return ("pre", "!", e)


def flat(e, parent=0):
    if not isinstance(e, tuple):
        return e
    k = e[0]
    if k == "let":
        return f"{flat(e[1])} = {flat(e[2])}"
    if k == "pre":
        return f"{e[1]}{wrap(e[2], 10)}"
    if k == "post":
        return f"{wrap(e[2], 10)}{e[1]}"
    if k == "op":
        op = e[1]
        if op in ASSIGN_OPS:
            return f"{flat(e[2])} {op} {flat(e[3])}"
        pr = PREC.get(op, 0)
        s = f"{wrap(e[2], pr)} {op} {wrap(e[3], pr + 1)}"
        return f"({s})" if parent > pr else s
    return str(e)


def wrap(e, pr):
    if isinstance(e, tuple) and e[0] == "op":
        if e[1] in ASSIGN_OPS:
            return f"({flat(e)})"
        p = PREC.get(e[1], 0)
        return f"({flat(e)})" if p < pr or p == 0 else flat(e)
    if isinstance(e, tuple) and e[0] == "let":
        return f"({flat(e)})"
    return flat(e)


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    dc = Decompiler(sys.argv[1])
    classes = [x["name"] for x in dc.p.exports if dc.p.class_of(x) == "Class"]
    for pat in sys.argv[2:]:
        for name in [c for c in classes if fnmatch.fnmatchcase(c, pat)]:
            print("\n".join(dc.klass(name)))
            print()


if __name__ == "__main__":
    main()

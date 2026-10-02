"""Tiny partial UE3 (v536) bytecode dumper: enough to read short move functions."""
import struct, sys
from upk import Package

p = Package("TdGame.u")
NATIVE = {0x97:'>', 0x96:'<', 0x9A:'==',0xAB:'*f',0xAC:'/f',0xAE:'+f',0xAF:'-f',0xB0:'<f',0xB1:'>f',0xB2:'<=f',0xB3:'>=f',
          0xB6:'*=f',0xB8:'+=f',0xA9:'neg_f',0xBA:'Abs',0xBB:'Sin',0xBE:'Sqrt',0xBF:'Square',0xC2:'FClamp',0xC4:'FMin',0xC5:'FMax',
          0xD1:'*v',0xD2:'*fv', 0xD3:'/v',0xD7:'+v',0xD8:'-v',0xE1:'VSize',0xE2:'Normal',0xC3:'Lerp',0xDD:'+=v',0x90:'+i',0x92:'-i',
          0x93:'*i',0xF7:'VSize2D?', 0xE3:'Dot?' }
def obj(i): return p.path(i) if i else "None"
def name(b,o):
    i,n=struct.unpack_from("<ii",b,o); return p.names[i] if 0<=i<len(p.names) else f"?{i}"
def dump(fn):
    for k,e in enumerate(p.exports):
        if p.path(k+1)==fn: break
    else: print("no",fn); return
    b=p.data[e["off"]:e["off"]+e["size"]]
    # UFunction layout: skip to script: find script size field heuristically -> print raw token walk from a guess
    print(fn, "size", len(b))
    out=[]; o=0
    while o < len(b):
        t=b[o]; o+=1
        if t in (0x00,0x01,0x02,0x12,0x48):  # local/instance/default var, class ctx?
            out.append({0:'L',1:'I',2:'D',0x12:'?',0x48:'O'}[t]+":"+obj(struct.unpack_from("<i",b,o)[0]).split('.')[-1]); o+=4
        elif t==0x1E: out.append("%g"%struct.unpack_from("<f",b,o)[0]); o+=4
        elif t==0x1D: out.append("i%d"%struct.unpack_from("<i",b,o)[0]); o+=4
        elif t==0x24: out.append("b%d"%b[o]); o+=1
        elif t==0x1B: out.append("call:"+name(b,o)); o+=8
        elif t==0x1C: out.append("final:"+obj(struct.unpack_from("<i",b,o)[0]).split('.')[-1]); o+=4
        elif t==0x35: out.append("."+obj(struct.unpack_from("<i",b,o)[0]).split('.')[-1]); o+=4+4+2
        elif t==0x19: out.append("ctx("); o+=2+4+1
        elif t==0x0F: out.append("LET")
        elif t==0x16: out.append(")")
        elif t==0x04: out.append("RETURN")
        elif t==0x07: out.append("IFNOT@%d"%struct.unpack_from("<H",b,o)[0]); o+=2
        elif t==0x06: out.append("JMP@%d"%struct.unpack_from("<H",b,o)[0]); o+=2
        elif t==0x38: out.append("cast%d"%b[o]); o+=1
        elif t==0x25: out.append("0")
        elif t==0x26: out.append("1")
        elif t==0x27: out.append("true")
        elif t==0x28: out.append("false")
        elif t==0x0B: out.append("nothing")
        elif t in NATIVE: out.append(NATIVE[t])
        else: out.append("%02x"%t)
    print(" ".join(out))
for fn in sys.argv[1:]: dump(fn)

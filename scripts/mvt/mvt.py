"""Minimal Mapbox Vector Tile decoder, standard library only."""
import struct

def _varint(b,i):
    r=s=0
    while True:
        x=b[i]; i+=1; r|=(x&0x7f)<<s
        if not x&0x80: return r,i
        s+=7

def _fields(b):
    """Yields (field_number, wire_type, value_or_bytes)."""
    i=0; n=len(b)
    while i<n:
        k,i=_varint(b,i); fn,wt=k>>3,k&7
        if wt==0:   v,i=_varint(b,i)
        elif wt==1: v=b[i:i+8]; i+=8
        elif wt==2:
            L,i=_varint(b,i); v=b[i:i+L]; i+=L
        elif wt==5: v=b[i:i+4]; i+=4
        else: raise ValueError("wire type %d"%wt)
        yield fn,wt,v

def _packed(b):
    out=[];i=0
    while i<len(b):
        v,i=_varint(b,i); out.append(v)
    return out

def _value(b):
    for fn,wt,v in _fields(b):
        if fn==1: return v.decode("utf8","replace")
        if fn==2: return struct.unpack("<f",v)[0]
        if fn==3: return struct.unpack("<d",v)[0]
        if fn in (4,5): return v
        if fn==6: return (v>>1)^(-(v&1))
        if fn==7: return bool(v)
    return None

def decode(buf):
    """-> {layer_name: {"extent": int, "features": [{"type", "props", "geom"}]}}"""
    layers={}
    for fn,wt,v in _fields(buf):
        if fn!=3: continue
        name=None;extent=4096;keys=[];vals=[];feats=[]
        for f2,w2,v2 in _fields(v):
            if f2==1: name=v2.decode("utf8","replace")
            elif f2==3: keys.append(v2.decode("utf8","replace"))
            elif f2==4: vals.append(_value(v2))
            elif f2==5: extent=v2
            elif f2==2: feats.append(v2)
        out=[]
        for fb in feats:
            tags=[];gtype=0;geo=[]
            for f3,w3,v3 in _fields(fb):
                if f3==2: tags=_packed(v3) if w3==2 else [v3]
                elif f3==3: gtype=v3
                elif f3==4: geo=_packed(v3) if w3==2 else [v3]
            props={keys[tags[i]]:vals[tags[i+1]] for i in range(0,len(tags)-1,2)
                   if tags[i]<len(keys) and tags[i+1]<len(vals)}
            # Decode the geometry command stream
            rings=[];cur=[];x=y=0;i=0
            while i<len(geo):
                cmd=geo[i]; op,cnt=cmd&7,cmd>>3; i+=1
                if op==1:  # MoveTo
                    for _ in range(cnt):
                        dx=(geo[i]>>1)^(-(geo[i]&1)); dy=(geo[i+1]>>1)^(-(geo[i+1]&1)); i+=2
                        x+=dx;y+=dy
                        if cur: rings.append(cur)
                        cur=[(x,y)]
                elif op==2:  # LineTo
                    for _ in range(cnt):
                        dx=(geo[i]>>1)^(-(geo[i]&1)); dy=(geo[i+1]>>1)^(-(geo[i+1]&1)); i+=2
                        x+=dx;y+=dy; cur.append((x,y))
                elif op==7:  # ClosePath
                    if cur: cur.append(cur[0]); rings.append(cur); cur=[]
                else: break
            if cur: rings.append(cur)
            out.append({"type":gtype,"props":props,"geom":rings})
        layers[name]={"extent":extent,"features":out}
    return layers

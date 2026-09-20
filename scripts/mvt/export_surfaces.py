#!/usr/bin/env python3
"""从 JHU 底图矢量瓦片导出地表面要素为 GeoJSON。

底图是 EPSG:2248 (马里兰州平面, 英尺) 的 PBF 矢量瓦片，MapLibre 无法直接使用。
本脚本解码瓦片、把坐标逆投影到 WGS84，输出标准 GeoJSON。

    python3 export_surfaces.py --zoom 6 --out ../../surfaces

只用标准库。上游是别人的生产服务，请求间有间隔。
"""
import argparse,collections,json,math,os,time,urllib.request
import mvt,lcc

BASE=("https://map.jhu.edu/arcgis/rest/services/Hosted/"
      "Homewood_Campus_Detailed_Basemap_20260422/VectorTileServer")
ORIGX,ORIGY=1413716.9130364358,611477.1196289062
RES={0:22.22222222222222,1:11.11111111111111,2:5.555555555555555,3:2.7777777777777777,
     4:1.3888888888888888,5:0.6944444444444444,6:0.3472222222222222,7:0.1736111111111111,
     8:0.08680555555555555,9:0.043402777777777776}
# NAD83 -> WGS84 常数校正，由 3 个控制点实测，离散度 0.000m
DLON,DLAT=-0.000002192,+0.000007888

# source-layer 的 _symbol 编码，取自底图 style root.json 的 filter
SYMBOL={
 "Vegetation":{0:"Approximate Area",1:"Hedgerows",2:"Landscape Beds",3:"Woodland"},
 "Sidewalk":  {0:"Brick Paver",1:"Other"},
}
# 只导出地表相关图层；建筑/标注等已有更好的来源
WANT=["Vegetation","Sidewalk","Stairs","Sidewalk Ramp","Road Area",
      "Campus Area","Trees","Shrubs","Athletic Facilities","Bridge",
      "Breezeway & Skywalk","River /Stream"]
GEOM={1:"Point",2:"LineString",3:"Polygon"}


def fetch(z,x,y,pause):
    u="%s/tile/%d/%d/%d.pbf"%(BASE,z,y,x)
    req=urllib.request.Request(u,headers={"User-Agent":"indoors-dump/1.0"})
    try:
        b=urllib.request.urlopen(req,timeout=90).read()
    except urllib.error.HTTPError as e:
        if e.code==404: return None          # 空瓦片，正常
        raise
    finally:
        time.sleep(pause)
    return mvt.decode(b) if b else None


def ring_area(r):
    return sum(r[i][0]*r[i+1][1]-r[i+1][0]*r[i][1] for i in range(len(r)-1))/2


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--zoom",type=int,default=6)
    ap.add_argument("--out",default="surfaces")
    ap.add_argument("--bbox",nargs=4,type=float,metavar=("XMIN","YMIN","XMAX","YMAX"),
                    help="EPSG:2248 范围，默认整个校园")
    ap.add_argument("--pause",type=float,default=0.3)
    args=ap.parse_args()

    z=args.zoom; span=512*RES[z]
    if args.bbox: xmin,ymin,xmax,ymax=args.bbox
    else: xmin,ymin,xmax,ymax=1414753.0,602307.3,1424058.6,609269.2   # 服务 fullExtent
    tx0,tx1=int((xmin-ORIGX)/span),int((xmax-ORIGX)/span)
    ty0,ty1=int((ORIGY-ymax)/span),int((ORIGY-ymin)/span)
    tiles=[(x,y) for x in range(tx0,tx1+1) for y in range(ty0,ty1+1)]
    print("z=%d  %d 张瓦片 (x %d-%d, y %d-%d)"%(z,len(tiles),tx0,tx1,ty0,ty1))

    os.makedirs(args.out,exist_ok=True)
    buckets=collections.defaultdict(list)
    seen=set()
    empty=0
    for i,(tx,ty) in enumerate(tiles,1):
        L=fetch(z,tx,ty,args.pause)
        if not L: empty+=1; continue
        if i%10==0 or i==len(tiles): print("  %d/%d"%(i,len(tiles)))
        for lname,d in L.items():
            if lname not in WANT: continue
            ext=d["extent"]
            for f in d["features"]:
                if not f["geom"]: continue
                rings=[]
                for r in f["geom"]:
                    pts=[]
                    for px,py in r:
                        sx=ORIGX+tx*span+px/ext*span
                        sy=ORIGY-ty*span-py/ext*span
                        lon,lat=lcc.to_wgs84(sx,sy)
                        pts.append([round(lon+DLON,7),round(lat+DLAT,7)])
                    rings.append(pts)
                sym=f["props"].get("_symbol")
                key=(lname,json.dumps(rings,separators=(",",":")))
                if key in seen: continue      # 瓦片缓冲区造成的完全重复
                seen.add(key)
                props={"layer":lname}
                if sym is not None:
                    props["symbol"]=sym
                    if lname in SYMBOL: props["class"]=SYMBOL[lname].get(sym,str(sym))
                props["_tile"]="%d/%d/%d"%(z,tx,ty)
                # 面/线/点靠环的闭合与点数判断，瓦片里 type 字段不可靠
                closed=all(len(r)>3 and r[0]==r[-1] for r in rings)
                if closed:
                    outer=[r for r in rings if ring_area(r)>0] or rings[:1]
                    holes=[r for r in rings if ring_area(r)<=0 and r not in outer]
                    geom={"type":"Polygon","coordinates":[outer[0]]+holes} if len(outer)==1 \
                         else {"type":"MultiPolygon","coordinates":[[r] for r in rings]}
                elif all(len(r)==1 for r in rings):
                    geom={"type":"MultiPoint","coordinates":[r[0] for r in rings]} if len(rings)>1 \
                         else {"type":"Point","coordinates":rings[0][0]}
                else:
                    geom={"type":"MultiLineString","coordinates":rings} if len(rings)>1 \
                         else {"type":"LineString","coordinates":rings[0]}
                buckets[lname].append({"type":"Feature","properties":props,"geometry":geom})

    print("\n空瓦片 %d 张"%empty)
    index={}
    for lname,feats in sorted(buckets.items()):
        fn=lname.replace(" ","_").replace("/","").replace("&","and")+".geojson"
        path=os.path.join(args.out,fn)
        json.dump({"type":"FeatureCollection","features":feats},open(path,"w"),separators=(",",":"))
        kinds=collections.Counter(f["geometry"]["type"] for f in feats)
        classes=collections.Counter(f["properties"].get("class") for f in feats)
        index[fn]={"layer":lname,"count":len(feats),"geometry":dict(kinds),
                   "classes":{k:v for k,v in classes.items() if k}}
        print("  %-28s %5d 要素  %-30s %s"%(fn,len(feats),dict(kinds),
              dict(classes) if any(classes) else ""))
    json.dump({"zoom":z,"source":BASE,"crs":"EPSG:4326","layers":index},
              open(os.path.join(args.out,"_index.json"),"w"),indent=2)
    print("\n输出 -> %s/"%args.out)


if __name__=="__main__":
    main()

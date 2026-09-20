"""EPSG:2248 (Maryland State Plane NAD83, US survey feet) -> EPSG:4326.

Inverse Lambert Conformal Conic 2SP, standard library only. NAD83 and WGS84
differ by under a metre here; the caller corrects the constant offset."""
import math

A=6378137.0                     # GRS80 semi-major axis
F_INV=298.257222101
FT=1200.0/3937.0                # US survey feet -> metres
P1=math.radians(39+27/60.0)     # standard parallel 1
P2=math.radians(38+18/60.0)     # standard parallel 2
P0=math.radians(37+40/60.0)     # latitude of origin
L0=math.radians(-77.0)          # central meridian
FE=1312333.3333333333*FT        # false easting (400000 m)
FN=0.0

_f=1/F_INV
E=math.sqrt(2*_f-_f*_f)

def _m(p): return math.cos(p)/math.sqrt(1-E*E*math.sin(p)**2)
def _t(p):
    s=math.sin(p)
    return math.tan(math.pi/4-p/2)/((1-E*s)/(1+E*s))**(E/2)

_m1,_m2=_m(P1),_m(P2)
_t1,_t2,_t0=_t(P1),_t(P2),_t(P0)
N=(math.log(_m1)-math.log(_m2))/(math.log(_t1)-math.log(_t2))
FF=_m1/(N*_t1**N)
RHO0=A*FF*_t0**N

def to_wgs84(x_ft,y_ft):
    """State plane feet -> (lon, lat) in degrees."""
    x=x_ft*FT-FE; y=y_ft*FT-FN
    r=RHO0-y
    rho=math.copysign(math.hypot(x,r),N)
    t=(rho/(A*FF))**(1/N)
    theta=math.atan2(x,r)
    lon=theta/N+L0
    p=math.pi/2-2*math.atan(t)
    for _ in range(12):                       # iterate for latitude
        s=math.sin(p)
        p2=math.pi/2-2*math.atan(t*((1-E*s)/(1+E*s))**(E/2))
        if abs(p2-p)<1e-13: p=p2; break
        p=p2
    return math.degrees(lon),math.degrees(p)

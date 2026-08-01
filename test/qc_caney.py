#!/usr/bin/env python3
"""
QC the Caney page's DATA payload: every published number, checked against an
independent recomputation or an invariant it must satisfy.

Pairs with test/qc_caney.mjs, which QCs what the page RENDERS and every plan it can
suggest. This half is instant and needs no browser.

    python3 test/qc_caney.py          # exits non-zero on any failure
"""
import json, sys, datetime, urllib.request, urllib.parse, math
sys.path.insert(0,'/Users/stevenrhodes/caney')
from zoneinfo import ZoneInfo
CT=ZoneInfo("America/Chicago")
h=open('/Users/stevenrhodes/caney/out/caney.html').read()
i=h.index('DATA='); j=h.index('{',i); d=0
for k in range(j,len(h)):
    if h[k]=='{':d+=1
    elif h[k]=='}':
        d-=1
        if d==0:break
D=json.loads(h[j:k+1])
FAIL=[];WARN=[];OK=[]
def chk(name,cond,detail=""):
    (OK if cond else FAIL).append((name,detail))
def warn(name,cond,detail=""):
    if not cond: WARN.append((name,detail))

P=D['points']; N=len(P)
# ---- geometry ----
chk("mfd is monotonic increasing downstream", all(P[i]['mfd']<=P[i+1]['mfd'] for i in range(N-1)),
    str([p['mfd'] for p in P]))
chk("rm is monotonic decreasing downstream", all(P[i]['rm']>=P[i+1]['rm'] for i in range(N-1)),
    str([p['rm'] for p in P]))
chk("all d0 reference depths positive", all(p['d0']>0 for p in P))
# ---- flow arrays ----
for p in P:
    chk("flow array length 180: "+p['name'], len(p['flow'])==180, str(len(p['flow'])))
    chk("no negative flow: "+p['name'], all(f>=0 for f in p['flow']))
# baseflow floor: every point should converge to the same steady flow (backtest finding)
mins=[min(p['flow']) for p in P]
spread=max(mins[:7])-min(mins[:7])   # trout reach only
warn("trout-reach minimum flows agree (constant baseflow)", spread<60, "spread %.0f cfs %s"%(spread,[round(m) for m in mins[:7]]))
# ---- riseCurve monotonic ----
rc=D['riseCurve']
chk("riseCurve monotonic in flow", all(rc[i][0]<rc[i+1][0] for i in range(len(rc)-1)))
chk("riseCurve monotonic in rise",  all(rc[i][1]<=rc[i+1][1] for i in range(len(rc)-1)))
chk("riseCurve starts at zero rise", rc[0][1]==0.0, str(rc[0]))
# ---- arrival stages ----
A=D['arrival']; st=D['arrivalStages']
chk("arrival mph matches published mph", abs(A['mph']-D['mph'])<1e-9, "%s vs %s"%(A['mph'],D['mph']))
chk("first-stage mph equals the deployed WATER_MPH", abs(st['first']['mph']-D['mph'])<1e-9,
    "%s vs %s"%(st['first']['mph'],D['mph']))
for nm,s in st.items():
    chk("stage band ordered (early>=median>=late mph): "+nm, s['early']>=s['mph']>=s['late'],
        "%s %s %s"%(s['early'],s['mph'],s['late']))
# arrival spots must match ACCESS mfd exactly
# An arrival spot is either a verified ACCESS or one of the user's trout holes. Both carry
# an mfd, which is all the arrival model needs; only ACCESS may be a put-in or take-out.
bym={p['name']:p['mfd'] for p in P}
bym.update({o['name']:o['mfd'] for o in (D.get('holes') or [])})
for sp in A['spots']:
    chk("arrival spot mfd matches its source: "+sp['name'], abs((bym.get(sp['name']) or -1)-sp['mfd'])<1e-6,
        "%s vs %s"%(sp['mfd'],bym.get(sp['name'])))
# release windows sane
for w in A['rel']:
    chk("release window ordered (start<end)", w[0]<w[1], str(w))
    chk("release window peak positive", w[2]>0, str(w))
chk("release windows chronological", all(A['rel'][i][0]<=A['rel'][i+1][0] for i in range(len(A['rel'])-1)))
# ---- gen schedule ----
for gi,g in enumerate(D['gen']):
    chk("gen spark has 24 hours: day%d"%gi, len(g['spark'])==24, str(len(g['spark'])))
    chk("gen peak equals max spark: day%d"%gi, g['peak']==max(g['spark']), "%s vs %s"%(g['peak'],max(g['spark'])))
    if g.get('relStart') is not None:
        chk("relStart within the day: day%d"%gi, 0<=g['relStart']<1440, str(g['relStart']))
    hrs=sum(w['hrs'] for w in g['windows']) if g['windows'] else 0
    chk("genhrs equals sum of window hours: day%d"%gi, g['genhrs']==hrs, "%s vs %s"%(g['genhrs'],hrs))
    for w in g['windows']:
        chk("window units >=1 when listed: day%d"%gi, w['units']>=1, str(w))
# gen arrival row must use the published mph
for gi,g in enumerate(D['gen'][:3]):
    if not g.get('arr') or g.get('relStart') is None: continue
    d0=None
    for nm,t in g['arr']:
        full=[p for p in P if p['name'].startswith(nm.split("'")[0][:6])]
        if not full: continue
        exp_min=g['relStart']+full[0]['mfd']/D['mph']*60
        eh=int(exp_min//60)%24
        got=t.lower().replace('am','').replace('pm','')
        gh=int(got)%12 + (12 if 'pm' in t.lower() else 0)
        warn("gen arr time matches mfd/mph: day%d %s"%(gi,nm), abs((gh-eh)%24)<=1,
             "shown %s, expected ~%d:00"%(t,eh))
# ---- week / dayscores ----
chk("week has 7 days", len(D['week'])==7)
chk("dayscores has 7", len(D['dayscores'])==7)
chk("calendar has 7", len(D['calendar'])==7)
chk("itinerary has 7", len(D['itinerary'])==7)
chk("wxDays has 7", len(D['wxDays'])==7)
chk("solDays has 7", len(D['solDays'])==7)
for i,w in enumerate(D['week']):
    chk("week hi>=lo: day%d"%i, (w.get('hi') is None or w.get('lo') is None or w['hi']>=w['lo']),
        "%s/%s"%(w.get('hi'),w.get('lo')))
    chk("week pop 0-100: day%d"%i, 0<=(w.get('pop') or 0)<=100, str(w.get('pop')))
# ---- now block ----
n=D['now']
chk("now cfs non-negative", (n.get('cfs') or 0)>=0, str(n.get('cfs')))
if n.get('stone') is not None and n.get('model') is not None:
    warn("model within 400 cfs of gauge", abs(n['stone']-n['model'])<400,
         "gauge %s vs model %s"%(n['stone'],n['model']))
chk("wadeMax matches the measured wade threshold", D['wadeMax']==600, str(D['wadeMax']))
# ---- trout holes (user-supplied spots) ----
H=D.get('holes') or []
chk("7 trout holes published", len(H)==7, str(len(H)))
for i,o in enumerate(H,1):
    chk("hole %d named in order"%i, o['name']=="Trout Hole #%d"%i, o['name'])
    chk("hole %d has coordinates"%i, -90<o['lat']<90 and -180<o['lon']<180)
    chk("hole %d mfd inside the trout reach"%i, 0<=o['mfd']<=15.0, str(o['mfd']))
chk("holes ordered by distance below the dam", all(H[i]['mfd']<=H[i+1]['mfd'] for i in range(len(H)-1)),
    str([o['mfd'] for o in H]))
# a hole must NEVER be selectable as a put-in or take-out
names={p['name'] for p in P}
chk("no hole leaked into ACCESS (they are not launches)", not any(o['name'] in names for o in H))
# every hole must be reachable by the arrival strip
spots={s['name'] for s in D['arrival']['spots']}
for o in H: chk("hole in the arrival selector: "+o['name'], o['name'] in spots)
for o in H:
    m=next(s for s in D['arrival']['spots'] if s['name']==o['name'])
    chk("arrival mfd matches the hole: "+o['name'], abs(m['mfd']-o['mfd'])<1e-6)

# ---- slider ----
chk("slider range sane", D['sliderMin']<D['launchDefault']<D['sliderMax'])
chk("planDefault indexes a real day", 0<=D['planDefault']<len(D['gen']))

print("QC LAYER A — DATA integrity")
print("  passed : %d"%len(OK))
print("  warned : %d"%len(WARN))
print("  FAILED : %d"%len(FAIL))
for nm,dt in WARN: print("   ! %-52s %s"%(nm,dt))
for nm,dt in FAIL: print("   \u2717 %-52s %s"%(nm,dt))
sys.exit(1 if FAIL else 0)

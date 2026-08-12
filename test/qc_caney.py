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
chk("no dead itinerary payload", 'itinerary' not in D)
for _c in D['craftOrder']:
    chk("every day has a non-trivial %s plan"%_c,
        all(len(((c.get('stepsBy') or {}).get(_c)) or [])>=2 for c in D['calendar']),
        str([len(((c.get('stepsBy') or {}).get(_c)) or []) for c in D['calendar']]))
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
# ---- Kirby Road (wade-only access) ----
K=[p for p in P if p['name']=='Kirby Road']
chk("Kirby Road present in ACCESS", len(K)==1)
if K:
    k=K[0]
    chk("Kirby is wade-only (no ramp, no paddle)", k['types']==['wade'], str(k['types']))
    chk("Kirby sits between I-40 and Betty's Island", 7.0<k['mfd']<9.0, str(k['mfd']))
    chk("Kirby is in the trout reach", k['reach']=='trout', k['reach'])
    chk("Kirby info warns it is not a launch", 'not' in (k.get('info') or '').lower()
        and 'launch' in (k.get('info') or '').lower(), (k.get('info') or '')[:60])

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

# ---- scoring curves, probed directly ----
# The craft toggle's whole claim is that the SAME water is worth different amounts depending
# on how you are on it. That cannot be tested against the live forecast -- some weeks have no
# zero-generation day at all -- so probe the curves themselves across the full flow range.
ROOT="/Users/stevenrhodes/caney"
_lv=None
try:
    # exec only the pure scoring helpers, not the whole generator (which hits the network)
    import re as _re
    _src=open(ROOT+"/briefing.py",encoding='utf-8').read()
    _ns={"riverlib":__import__("riverlib")}
    for _fn in ("_lerp","_cf","_sc_level","_sc_clarity","_sc_weather"):
        _m=_re.search(r"^def %s\([^\n]*\n(?:[ \t][^\n]*\n|[ \t]*\n)*"%_re.escape(_fn),_src,_re.M)
        if _m: exec(_m.group(0),_ns)
    _ns["_WM"]=_ns["riverlib"].WATER_MODEL["caney"]
    # Wade scoring now reads the whole reach via wade_open(), which needs live ACCESS geometry
    # and the flow model. Stub a uniform 7-spot reach and smuggle the test flow in through the
    # d0 argument, so the CURVE can still be probed without touching the network.
    _ns["WADE_SPOTS"]=[{"name":"S%d"%i,"mfd":i*2.5} for i in range(7)]
    def _stub_open(_q,_h):
        _M=_ns["_WM"]
        if _q<=_M["wade_ok"]: _w=1.0
        elif _q<=_M["wade_marginal"]: _w=_ns["_lerp"](_q,_M["wade_ok"],_M["wade_marginal"],1.0,0.45)
        else: return []
        return [(s,_q,_w) for s in _ns["WADE_SPOTS"]]
    _ns["wade_open"]=_stub_open
    _ns["_where"]=lambda o: "the whole reach" if o else ""
    _ns["_ap12"]=lambda h: "%dpm"%h
    _lv=_ns.get("_sc_level"); _cl=_ns.get("_sc_clarity"); _sw=_ns.get("_sc_weather")
except Exception as e:
    chk("scoring helpers are probeable", False, str(e))

if _lv:
    f=lambda c,lo,hi: _lv(c,lo,hi)[0]
    fw=lambda q: _lv("wade",q,q,q,6,6)[0]          # d0 carries the reach flow for the stub
    # direction: minimum flow favours the wader, hurts the jet boat
    chk("minimum flow: wade beats powerboat", fw(250)>f("power",250,600),
        "wade %.2f vs power %.2f"%(fw(250),f("power",250,600)))
    # direction: a big release favours the boat, ends wading
    chk("heavy release: powerboat beats wade", f("power",4000,7000)>fw(4000),
        "power %.2f vs wade %.2f"%(f("power",4000,7000),fw(4000)))
    # wade score must fall monotonically as the reach comes up
    _w=[fw(q) for q in (200,400,500,600,900,1400)]
    chk("wade score falls monotonically as the reach rises", all(_w[i]>=_w[i+1] for i in range(len(_w)-1)), str(_w))
    chk("a wadeable reach scores well", fw(300)>=0.9, "%.2f"%fw(300))
    chk("an unwadeable reach scores near zero", fw(1200)<=0.05, "%.2f"%fw(1200))
    # a blown-out river is bad for everyone
    for c in ("raft","power"):
        chk("blown out is poor for %s"%c, f(c,9000,16000)<0.5, "%.2f"%f(c,9000,16000))
    chk("blown out is poor for wade", fw(9000)<0.5, "%.2f"%fw(9000))
    # every craft, every plausible flow: bounded 0..1
    chk("level score stays in range", all(0.0<=f(c,lo,hi)<=1.0
        for c in ("raft","power") for lo in (200,500,1200,5000,12000) for hi in (600,3000,8000,20000) if hi>=lo)
        and all(0.0<=fw(q)<=1.0 for q in (200,400,600,1200,5000,12000)))
    # clarity is monotone in antecedent rain
    _c=[_cl(r)[0] for r in (0.0,0.2,0.6,1.5,3.0)]
    chk("clarity falls monotonically with recent rain", all(_c[i]>=_c[i+1] for i in range(len(_c)-1)), str(_c))
    # a thunderstorm is a gate: it must outweigh every comfort term combined
    _perfect={"precipMax":0,"gust":3,"hi":72}
    _storm=dict(_perfect,storm=True,stormSpan="1pm-6pm")
    for c in ("wade","raft","power"):
        chk("thunderstorm gates the weather score for %s"%c, _sw(c,_storm)[0]<=0.2,
            "%.2f"%_sw(c,_storm)[0])
        chk("a calm day scores full weather for %s"%c, _sw(c,_perfect)[0]>=0.99, "%.2f"%_sw(c,_perfect)[0])
    chk("storm text names lightning", "lightning" in _sw("wade",_storm)[1])

# ---- wade window must not contradict itself, and must not claim dawn ----
# Measured at Stonewall over 14 days (USGS 03424860, hourly medians): the river is wadeable
# (<=600 cfs) 0% of the time from midnight to 9am, 93% from 2-4pm, and 0% again after 8pm. On a
# daily-peaking schedule the previous evening's release is still passing Stonewall at first
# light, so the wadeable window is a MIDDAY LULL. The page used to advise "wade dawn to the
# bump" on every generating day, which is exactly backwards. Guard both halves: the verdict must
# agree with the computed window, and it must never send someone to wade at dawn on a gen day.
import re as _re2
for _d in D['week']:
    _b=_d['byCraft']['wade']; _w=next(p for p in _b['why']['parts'] if p['k']=='Window')
    _v=_b['verdict']
    if _d['units'] and _w['pts']>0:
        _sr=int(((D['wxDays'][_d['i']] or {}).get('sunrise') or '06:00')[:2])
        _first=_re2.search(r'(\d{1,2})(am|pm)',_w['why']) if _re2 else None
        if 'dawn' in _v.lower() and _first:
            _fh=int(_first.group(1))%12+(12 if _first.group(2)=='pm' else 0)
            chk("verdict says dawn only when the window starts at first light: "+_d['label'],
                abs(_fh-_sr)<=1, "window starts %s, sunrise %02d:00"%(_first.group(0),_sr))
        # any clock time in the ACTION half of the verdict must appear in the computed window.
        # The limiter half ("Storms 5pm-6pm . ...") names the storm, not the wade window.
        _act=_v.split(' \u00b7 ')[-1]
        _ts=_re2.findall(r'\d{1,2}(?:am|pm)',_act)
        chk("wade verdict times come from the computed window: "+_d['label'],
            all(t in _w['why'] for t in _ts), _act+" | "+_w['why'])
    chk("wade window is internally consistent: "+_d['label'],
        (_w['pts']==0)==(_w['why'].startswith('no daylight hour')), _w['why'])

# ---- timed plan ----
# The plan used to be one narrative that assumed a powerboat and then told you to wade: every
# day opened "launch at Stonewall and run up", continued "wade the bars", and finished "on the
# oars" -- three craft in one plan, none of them chosen by the user. It is now per craft.
import re as _rp
_STRIP=lambda x:_rp.sub('<[^>]+>','',x)
_WADEMAX=600     # riverlib.WATER_MODEL['caney']['wade_marginal']
for _c in D['craftOrder']:
    for _i,_cal in enumerate(D['calendar']):
        _sb=(_cal.get('stepsBy') or {}).get(_c)
        chk("every day has a %s plan: day %d"%(_c,_i), bool(_sb))
        if not _sb: continue
        _txt=" ".join(_STRIP(x['x']) for x in _sb)
        # craft language must not bleed across plans
        if _c=='wade':
            chk("wade plan never says launch/run up: day %d"%_i,
                not _rp.search(r'\blaunch\b|\brun up\b|\bon the oars\b|take-out',_txt,_rp.I), _txt[:120])
            # every spot the wade plan sends you to must actually be wadeable
            for _m in _rp.finditer(r'Drop down to ([A-Za-z0-9 .\'→-]+?) \(~([\d,]+) cfs\)',_txt):
                _q=int(_m.group(2).replace(',',''))
                chk("wade plan only sends you to wadeable water: day %d %s"%(_i,_m.group(1).strip()),
                    _q<=_WADEMAX, "%s cfs"%_m.group(2))
            # and it must not tell you to keep fishing after saying the water is gone
            _idx=[n for n,x in enumerate(_sb) if 'last wadeable water gone' in _STRIP(x['x'])]
            if _idx:
                _after=[_STRIP(x['x']) for x in _sb[_idx[0]+1:]]
                chk("nothing follows 'out of the river' but safety/dusk: day %d"%_i,
                    all(('Storm' in a or 'storm' in a or 'Last light' in a) for a in _after), " | ".join(_after)[:140])
        if _c=='raft':
            chk("float plan never instructs running back up: day %d"%_i,
                not _rp.search(r"(?<!can't )(?<!cannot )run back up",_txt,_rp.I), _txt[:120])
        if _c=='power':
            chk("powerboat plan does not tell you to wade: day %d"%_i,
                not _rp.search(r'\bwade\b|\bwading\b',_txt,_rp.I), _txt[:120])
        # a plan must read as a sequence: ordered, no repeats
        def _mins(t):
            m=_rp.match(r'(\d+):(\d+)(am|pm)',t)
            if not m: return None
            hh=int(m.group(1))%12+(12 if m.group(3)=='pm' else 0)
            return hh*60+int(m.group(2))
        _ts=[_mins(x['t']) for x in _sb]
        chk("%s plan is in time order: day %d"%(_c,_i),
            all(a is not None and b is not None and a<=b for a,b in zip(_ts,_ts[1:])), str([x['t'] for x in _sb]))
        chk("%s plan has no repeated step: day %d"%(_c,_i),
            len({_STRIP(x['x']) for x in _sb})==len(_sb))
        # storms are a safety gate: they must be present and must sort first in their hour
        if D['week'][_i].get('storm'):
            _si=[n for n,x in enumerate(_sb) if 'Storms due' in _STRIP(x['x'])]
            chk("storm day carries a storm warning: %s day %d"%(_c,_i), bool(_si))
            if _si:
                n=_si[0]
                _same=[m for m,x in enumerate(_sb) if x['t']==_sb[n]['t']]
                chk("storm warning sorts first in its hour: %s day %d"%(_c,_i), n==min(_same),
                    str([_sb[m]['t'] for m in _same]))
        else:
            chk("no storm warning on a storm-free day: %s day %d"%(_c,_i),
                'Storms due' not in _txt)

# ---- the plan must COMPUTE its recommendation, not assert one ----
# Every day used to open "First light - launch at Stonewall and run up", identical all week,
# which with a noon release meant sitting at the top of the river for six hours. The launch
# time is now solved from the release, so it has to actually satisfy the arithmetic.
_UP=D['upMph']; _MPH=D['mph']
_bym2={p['name']:p['mfd'] for p in D['points']}
_launches=set(); _putins=set()
for _i,_cal in enumerate(D['calendar']):
    _pw=" ".join(_STRIP(x['x']) for x in (_cal.get('stepsBy') or {}).get('power') or [])
    _m=_rp.search(r'Launch by (\d{1,2}:\d{2}(?:am|pm)) at ([A-Za-z0-9 .\'-]+?) and run up.*?puts you at ([A-Za-z0-9 .\'-]+?) when the leading edge arrives \((\d{1,2}:\d{2}(?:am|pm))\)',_pw)
    if _m:
        _launches.add(_m.group(1))
        def _M(t):
            g=_rp.match(r'(\d{1,2}):(\d{2})(am|pm)',t); hh=int(g.group(1))%12+(12 if g.group(3)=='pm' else 0)
            return hh*60+int(g.group(2))
        _ramp,_spot=_m.group(2).strip(),_m.group(3).strip()
        chk("launch ramp is a real access: day %d"%_i, _ramp in _bym2, _ramp)
        chk("intercept spot is a real access: day %d"%_i, _spot in _bym2, _spot)
        if _ramp in _bym2 and _spot in _bym2:
            _run=(_bym2[_ramp]-_bym2[_spot])/_UP*60.0        # minutes motoring upstream
            _gap=_M(_m.group(4))-_M(_m.group(1))
            chk("launch time satisfies the intercept arithmetic: day %d"%_i,
                abs(_gap-_run)<=20, "gap %d min vs run %.0f min"%(_gap,_run))
            chk("you launch before the edge arrives: day %d"%_i, _gap>0, str(_gap))
    _pr=" ".join(_STRIP(x['x']) for x in (_cal.get('stepsBy') or {}).get('raft') or [])
    _mr=_rp.search(r'Put in at (\d{1,2}:\d{2}(?:am|pm))',_pr)
    if _mr: _putins.add(_mr.group(1))
    # a float plan must not say you'll miss the rise and then narrate riding it
    if 'reach the take-out before the rise ever catches you' in _pr:
        chk("float plan that says you'd miss it also gives a put-in: day %d"%_i, bool(_mr), _pr[:140])
# release times vary across the week, so the recommendation must vary too
_relspans={ g['span'] for g in D['gen'] if g.get('span') }   # only days that actually generate
if len(_relspans)>1:
    chk("launch time responds to the release schedule", len(_launches)>1,
        "spans %s -> launches %s"%(sorted(_relspans),sorted(_launches)))
    chk("float put-in responds to the release schedule", len(_putins)>1,
        "spans %s -> put-ins %s"%(sorted(_relspans),sorted(_putins)))

# ---- Smith Fork: the thing that actually decides clarity ----
# From a guide who fishes it: the river runs clear until the Smith Fork confluence, and turns
# brown below it when the creek is up -- "sometimes the Smith Fork flows with more force than the
# Caney Fork, and when that happens the fishing is going to be tough." Both halves are tested:
# WHERE the line is, and that the model only calls it brown when the creek is both loaded AND
# undiluted by the release.
_S = D.get('smith') or {}
chk("Smith Fork gauge is wired in", _S.get('site') == '03424730', str(_S.get('site')))
chk("Smith Fork has a live reading", _S.get('now') is not None)
chk("confluence sits between Betty's Island and Stonewall",
    9.0 < (_S.get('confMfd') or 0) < 15.0, str(_S.get('confMfd')))
chk("the reach above the confluence is always clear", _S.get('above') == 'clear', str(_S.get('above')))
_conf = _S.get('confMfd') or 11.08
for _p in D['points']:
    chk("access is on the right side of the confluence: " + _p['name'],
        _p.get('belowSmith') == (_p['mfd'] > _conf),
        "mfd %s belowSmith=%s" % (_p['mfd'], _p.get('belowSmith')))
chk("the upper wade reach is above the confluence",
    all(not _p.get('belowSmith') for _p in D['points']
        if 'wade' in (_p.get('types') or []) and _p['mfd'] <= 9.0))
chk("Stonewall is correctly flagged as wadeable BUT below the confluence",
    any(_p.get('belowSmith') and 'wade' in (_p.get('types') or []) for _p in D['points']))
chk("the page does not claim the whole wade reach stays clear",
    'whole wade reach' not in open('/Users/stevenrhodes/caney/out/caney.html').read())
chk("every trout hole is above the confluence",
    all(o['mfd'] < _conf for o in (D.get('holes') or [])),
    str([o['mfd'] for o in (D.get('holes') or []) if o['mfd'] >= _conf]))

# the curve itself, probed directly
import math as _m
_CL, _MD = 50.0, 1200.0
def _mud(sm, cy):
    sed = max(0.0, min(1.0, (_m.log(max(sm, 1.0)) - _m.log(_CL)) / (_m.log(_MD) - _m.log(_CL))))
    fr = sm / (sm + max(cy, 1.0))
    return sed * max(0.0, min(1.0, fr / 0.5))
chk("a creek at its baseline leaves the river clear", _mud(24.5, 470) < 0.12, "%.3f" % _mud(24.5, 470))
chk("the guide's day reads chocolate milk", _mud(1300, 470) >= 0.60, "%.3f" % _mud(1300, 470))
_seq = [_mud(q, 470) for q in (25, 100, 300, 700, 1300, 3000)]
chk("muddiness rises monotonically with the creek",
    all(_seq[i] <= _seq[i + 1] for i in range(len(_seq) - 1)), str([round(x, 3) for x in _seq]))
# dilution: the release is what makes the same creek invisible
chk("generation dilutes the creek", _mud(700, 4000) < _mud(700, 470),
    "%.3f under generation vs %.3f at minimum flow" % (_mud(700, 4000), _mud(700, 470)))
chk("a big release can clear water a small one cannot", _mud(400, 6000) < 0.12,
    "%.3f" % _mud(400, 6000))
chk("muddiness stays in range",
    all(0.0 <= _mud(q, c) <= 1.0 for q in (10, 100, 1000, 6000) for c in (200, 1000, 8000)))

# and the page has to SAY which side is which, or the number is useless
_html = open('/Users/stevenrhodes/caney/out/caney.html').read()
chk("the page explains the confluence split", 'confluence' in _html.lower())
chk("the page links the Smith Fork gauge", '03424730' in _html)

print("QC LAYER A — DATA integrity")
print("  passed : %d"%len(OK))
print("  warned : %d"%len(WARN))
print("  FAILED : %d"%len(FAIL))
for nm,dt in WARN: print("   ! %-52s %s"%(nm,dt))
for nm,dt in FAIL: print("   \u2717 %-52s %s"%(nm,dt))
sys.exit(1 if FAIL else 0)

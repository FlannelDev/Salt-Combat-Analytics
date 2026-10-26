import csv, json, os, re, sys, threading, webbrowser, urllib.parse, hashlib, datetime, time
from collections import defaultdict, Counter
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parent
LOG=ROOT/'WoWCombatLog.txt'
DATA={'events':[],'segments':[],'actors':[],'meta':{}}
PROFILES={}
HISTORY_PATH=ROOT/"gear_history.json"
GEAR_HISTORY=[]
LOCK=threading.Lock()
ACTIVE_LOG=None
IMPORT_STATE={'state':'idle','message':'','started':0,'finished':0,'bytesRead':0,'bytesTotal':0,'linesRead':0}
IMPORT_LOCK=threading.Lock()
WATCH_STATE={'enabled':False,'interval':8,'lastSignature':None}
PAT=re.compile(r'^(\d{1,2})/(\d{1,2})\s+(\d\d):(\d\d):(\d\d)\.(\d+)\s+(.*)$')
def number(s):
 try:return int(s,0) if s.startswith('0x') else int(s)
 except:return 0
def parse(path, progress=None):
 events=[]; actors={}; invalid=0; prev=None; dayoffset=0; owners={}; summons=[]
 with open(path,encoding='utf-8-sig',errors='replace',newline='') as f:
  for lineno,line in enumerate(f,1):
   if progress and lineno%2000==0:
    progress(lineno, f.tell() if False else 0)
   m=PAT.match(line.strip())
   if not m:invalid+=1;continue
   month,day,hh,mm,ss,ms,body=m.groups()
   try:parts=next(csv.reader([body],skipinitialspace=True))
   except:invalid+=1;continue
   if len(parts)<7:invalid+=1;continue
   clock=(int(day)*86400+int(hh)*3600+int(mm)*60+int(ss)+int(ms.ljust(3,'0')[:3])/1000)
   if prev is not None and clock+dayoffset<prev-3600:dayoffset+=31*86400
   t=clock+dayoffset;prev=t
   kind=parts[0];sg,sn,sflag,dg,dn,dflag=parts[1:7]
   sn='' if sn=='nil' else sn;dn='' if dn=='nil' else dn
   for guid,name,flag in ((sg,sn,sflag),(dg,dn,dflag)):
    if guid and guid!='0x0000000000000000' and name:
     if guid not in actors:actors[guid]={'id':guid,'name':name,'flags':number(flag),'player':bool(number(flag)&0x400)}
   # WoW combat-log flags: 0x400 player, 0x1000 pet, 0x2000 guardian.
   # SPELL_SUMMON carries the owner GUID as source and pet GUID as destination.
   if kind=='SPELL_SUMMON' and sg and dg and sg!=dg:
    summons.append((t,sg,dg))
    owners[dg]=sg
   tail=parts[7:];spell='Melee';sid=0;amount=0;over=0;absorbed=0;crit=False;miss='';school='';aura='';stacks=0
   if kind.startswith('SPELL_') or kind.startswith('RANGE_') or kind.startswith('DAMAGE_SHIELD'):
    if len(tail)>=3:
     sid=number(tail[0]);spell=tail[1];school=tail[2]
    ext=tail[3:]
   else:ext=tail
   if kind in ('SWING_DAMAGE','SPELL_DAMAGE','SPELL_PERIODIC_DAMAGE','RANGE_DAMAGE','DAMAGE_SHIELD','DAMAGE_SPLIT'):
    amount=number(ext[0]) if ext else 0
    # WotLK damage: amount, overkill, school, resisted, blocked, absorbed, critical, glancing, crushing
    absorbed=number(ext[5]) if len(ext)>5 else 0
    crit=len(ext)>6 and ext[6]=='1'
   elif kind in ('SPELL_HEAL','SPELL_PERIODIC_HEAL'):
    amount=number(ext[0]) if ext else 0
    over=number(ext[2]) if len(ext)>2 else 0
    crit=len(ext)>3 and ext[3]=='1'
   elif kind in ('SPELL_ABSORBED',):
    # Keep the original event for audit; combat-log formats differ across clients.
    pass
   elif kind.endswith('_MISSED'):
    miss=ext[0] if ext else ''
   elif 'AURA_' in kind:
    aura=ext[0] if ext else ''
    if kind.endswith('_DOSE'):stacks=number(ext[1]) if len(ext)>1 else 0
   elif kind=='SPELL_CAST_FAILED':miss=ext[0] if ext else ''
   events.append({'t':round(t,3),'k':kind,'s':sg,'sn':sn,'d':dg,'dn':dn,'spell':spell,'sid':sid,'amount':amount,'over':over,'absorb':absorbed,'crit':crit,'miss':miss,'aura':aura,'stacks':stacks,'line':lineno})
 if not events:return {'events':[],'segments':[],'actors':[],'meta':{'error':'No events parsed'}}
 # Resolve owner chains only when they terminate at a player. A pet whose
 # summon was not observed remains unattributed rather than being credited
 # to a random character with a similar name.
 player_ids={guid for guid,a in actors.items() if a['player']}
 def resolve_owner(guid):
  visited=set()
  while guid in owners and guid not in visited:
   visited.add(guid);guid=owners[guid]
  return guid if guid in player_ids else None
 owned={pet:resolve_owner(pet) for pet in owners}
 owned={pet:owner for pet,owner in owned.items() if owner}
 # Include regular mobs, short encounters, missed attacks and cast-only pulls.
 # Ignore passive aura noise; retain the original events for later drilldowns.
 combat_kinds={'SWING_DAMAGE','SWING_MISSED','RANGE_DAMAGE','RANGE_MISSED',
               'SPELL_DAMAGE','SPELL_PERIODIC_DAMAGE','SPELL_MISSED',
               'SPELL_PERIODIC_MISSED','SPELL_HEAL','SPELL_PERIODIC_HEAL',
               'SPELL_CAST_START','SPELL_CAST_SUCCESS','SPELL_CAST_FAILED',
               'DAMAGE_SHIELD','DAMAGE_SPLIT','UNIT_DIED','UNIT_DESTROYED'}
 active=[e for e in events if e['k'] in combat_kinds]
 segments=[]
 if active:
  start=last=active[0]['t'];count=0
  for e in active:
   if e['t']-last>18:
    if count:segments.append({'id':len(segments),'start':start,'end':last,'duration':max(0.001,last-start),'events':count})
    start=e['t'];count=0
   last=e['t'];count+=1
  if count:segments.append({'id':len(segments),'start':start,'end':last,'duration':max(.001,last-start),'events':count})
 # Identify the main hostile target from damage dealt by players and their owned pets.
 for seg in segments:
  targets=Counter()
  for e in events:
   if not(seg['start']<=e['t']<=seg['end']) or e['amount']<=0 or 'DAMAGE' not in e['k']:continue
   source=actors.get(owned.get(e['s'],e['s']),{})
   dest=actors.get(e['d'],{})
   if source.get('player') and not dest.get('player') and e['dn'] and e['dn']!='Unknown':
    targets[e['dn']]+=e['amount']
  if targets:seg['name']=targets.most_common(1)[0][0]
  else:
   hostiles=Counter(e['sn'] for e in events if seg['start']<=e['t']<=seg['end'] and e['sn'] and not actors.get(e['s'],{}).get('player') and e['k'] in combat_kinds)
   seg['name']=hostiles.most_common(1)[0][0] if hostiles else 'Unidentified combat'
 return {'owners':owned,'summons':summons,'unattributedPets':sorted({e['sn'] for e in events if e['amount']>0 and 'DAMAGE' in e['k'] and e['s'] in actors and not actors[e['s']]['player'] and e['s'] not in owned and (actors[e['s']]['flags'] & 0x3000)}),'events':events,'segments':segments,'actors':sorted(actors.values(),key=lambda a:(not a['player'],a['name'])),'meta':{'filename':Path(path).name,'lines':lineno,'parsed':len(events),'invalid':invalid,'segments':len(segments)}}


def extract_snapshot_payload(raw):
 # WoW SavedVariables use ["groupExport"] = "...", not groupExport = "...".
 # Never execute the Lua file; extract only the quoted string value.
 key = r'(?:\[\s*[\"\'](?:groupExport|snapshot)[\"\']\s*\]|\b(?:groupExport|snapshot)\b)'
 matches = list(re.finditer(key + r'\s*=\s*"((?:\\.|[^"\\])*)"', raw, re.S))
 if not matches:
  return raw
 # Prefer combined group export when present, irrespective of key ordering.
 match = next((m for m in matches if 'groupExport' in m.group(0).split('=')[0]), matches[0])
 return match.group(1).replace('\\\\', '\\').replace('\\n', '\n').replace('\\"', '"')

def parse_snapshot(raw):
 # Parse only our own addon format, never execute Lua SavedVariables code.
 payload=extract_snapshot_payload(raw)
 lines=payload.splitlines()
 header=next((x for x in lines if x.startswith('HCS1|')),None)
 if not header:raise ValueError('No HCS1 snapshot found. Install the included addon, use /hcs save and /reload, then import its SavedVariables Lua file.')
 h=header.split('|');decode=urllib.parse.unquote
 profile={'name':decode(h[1]),'realm':decode(h[2]),'class':decode(h[3]),'level':int(h[4]),'gear':[],'source':'UNKNOWN','capturedAt':''}
 for line in lines:
  x=line.split('|')
  if x[0]=='GEAR' and len(x)>=3:
   link=decode('|'.join(x[2:]));item=re.search(r'item:([0-9:-]+)',link)
   fields=item.group(1).split(':') if item else []
   nums=[int(v) if v.lstrip('-').isdigit() else 0 for v in fields[:6]]
   nums+= [0]*(6-len(nums))
   name=re.search(r'\[([^\]]+)\]',link)
   profile['gear'].append({'slot':int(x[1]),'name':name.group(1) if name else 'Unknown item','itemId':nums[0],'enchantId':nums[1],'gemIds':nums[2:6],'link':link,'tooltip':[],'tier':'','itemStats':{}})
  elif x[0]=='META' and len(x)>=3:profile['source']=x[1];profile['capturedAt']=x[2]
  elif x[0]=='ITEMNAME' and len(x)>=3:
   for gear in profile['gear']:
    if gear['slot']==int(x[1]):gear['name']=decode('|'.join(x[2:]));break
  elif x[0]=='TIER' and len(x)>=3:
   for gear in profile['gear']:
    if gear['slot']==int(x[1]):gear['tier']=decode('|'.join(x[2:]));break
  elif x[0]=='TOOLTIP' and len(x)>=3:
   for gear in profile['gear']:
    if gear['slot']==int(x[1]):gear.setdefault('tooltip',[]).append(decode('|'.join(x[2:])));break
 return profile

def store_gear_profiles(profiles):
 """Immutable historical versions, deduplicated by character, capture timestamp and gear."""
 existing={entry['id'] for entry in GEAR_HISTORY}
 count=0
 for profile in profiles:
  slim={k:profile[k] for k in ('name','realm','class','level','gear','source','capturedAt')}
  identity=json.dumps(slim,sort_keys=True,ensure_ascii=False)
  ident=hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
  if ident not in existing:
   GEAR_HISTORY.append({'id':ident,**slim});existing.add(ident);count+=1
  PROFILES[profile['name'].lower()]=profile
 if count:
  HISTRY=sorted(GEAR_HISTORY,key=lambda x:(x['capturedAt'],x['name']))
  HISTORY_PATH.write_text(json.dumps(HISTRY,ensure_ascii=False,indent=2),encoding='utf-8')
 return count

def fight_roster(data, segment_index):
 """Participants are player GUIDs with active combat events inside this segment."""
 segs=data['segments']
 if not (0<=segment_index<len(segs)):return []
 seg=segs[segment_index];start,end=seg['start'],seg['end']
 actors={a['id']:a for a in data['actors'] if a['player']}
 participation={}
 for e in data['events']:
  if e['t']<start or e['t']>end:continue
  # Combat action or damage/healing received; mere aura presence does not establish participation.
  meaningful=(e['amount']>0 and ('DAMAGE' in e['k'] or 'HEAL' in e['k'])) or e['k'] in ('SPELL_CAST_SUCCESS','SPELL_CAST_START','SWING_MISSED','SPELL_MISSED','RANGE_MISSED')
  if not meaningful:continue
  for guid in (e['s'],e['d']):
   if guid in actors:
    row=participation.setdefault(guid,{'id':guid,'name':actors[guid]['name'],'events':0})
    row['events']+=1
 return sorted(participation.values(),key=lambda x:x['name'].lower())

def gear_for_fight(data, segment_index):
 """Never claim a snapshot is verified at fight time without a matching clock."""
 if not (0<=segment_index<len(data['segments'])):return []
 seg=data['segments'][segment_index]
 # Combat log timestamps have no year; match the local month/day and time to snapshot dates.
 # A saved capture after the fight is not treated as a proven pre-fight loadout.
 participants=fight_roster(data,segment_index)
 for person in participants:
  history=[p for p in GEAR_HISTORY if p['name'].lower()==person['name'].lower()]
  eligible=[]
  for snap in history:
   try:
    dt=datetime.datetime.strptime(snap['capturedAt'],'%Y-%m-%d %H:%M:%S')
    stamp=dt.day*86400+dt.hour*3600+dt.minute*60+dt.second
    delta=seg['start']-stamp
    if 0<=delta<=86400*15:eligible.append((delta,snap))
   except (ValueError,KeyError):pass
  if eligible:
   age,snap=min(eligible,key=lambda x:x[0]);person['gear']=snap['gear'];person['capturedAt']=snap['capturedAt'];person['gearStatus']='Prior known snapshot (not verified at pull)';person['ageSeconds']=round(age)
  else:
   person['gear']=[];person['capturedAt']='';person['gearStatus']='No qualifying pre-fight snapshot';person['ageSeconds']=None
 return participants

def extract_history_payloads(raw):
 """Read serialized gearHistory payload strings without executing Lua."""
 start=raw.find('gearHistory')
 if start<0:return []
 # Serialized array entries are { ["payload"] = "..." }.
 section=raw[start:]
 pattern=r'(?:\[\s*["\']payload["\']\s*\]|\bpayload\b)\s*=\s*"((?:\\.|[^"\\])*)"'
 return [m.group(1).replace('\\\\','\\').replace('\\n','\n').replace('\\"','"') for m in re.finditer(pattern,section,re.S)]

def import_snapshot_file(path):
 raw=Path(path).read_text(encoding='utf-8-sig',errors='replace')
 payload=extract_snapshot_payload(raw)
 blocks=[b.strip() for b in payload.split('HCS_END') if any(line.startswith('HCS1|') for line in b.splitlines())]
 historical=extract_history_payloads(raw)
 profiles=[parse_snapshot(b) for b in (historical + blocks)] if (historical or blocks) else [parse_snapshot(payload)]
 with LOCK:
  new=store_gear_profiles(profiles)
  (ROOT/'profiles.json').write_text(json.dumps(PROFILES,indent=2),encoding='utf-8')
 return new

def watch_saved_snapshots():
 """Automatically ingest files once WoW has flushed them to SavedVariables."""
 previous={}
 while True:
  try:
   config=ROOT/'wow_path.txt'
   if config.exists():
    wow=Path(config.read_text(encoding='utf-8-sig').strip().strip('"'))
    folder=wow/'Logs'/'HeroesCombatSnapshots'
    paths=list(folder.glob('*/HeroesCombatSnapshot.lua')) if folder.exists() else []
    for path in paths:
     stamp=(path.stat().st_mtime_ns,path.stat().st_size)
     if previous.get(str(path))!=stamp:
      try:
       added=import_snapshot_file(path)
       previous[str(path)]=stamp
       if added:print('Imported',added,'historical gear snapshots from',path)
      except Exception as exc:print('Snapshot import deferred:',path,exc)
  except Exception as exc:print('Snapshot watcher:',exc)
  time.sleep(3)

def buff_uptime(events, start, end, actor='all', target='all'):
 """Observed aura coverage within a window; unknown initial state is not assumed active."""
 duration=max(0.001,end-start)
 states={}; totals={}; intervals={}
 aura_events={'SPELL_AURA_APPLIED','SPELL_AURA_REFRESH','SPELL_AURA_REMOVED','SPELL_AURA_APPLIED_DOSE','SPELL_AURA_REMOVED_DOSE','SPELL_AURA_BROKEN','SPELL_AURA_BROKEN_SPELL'}
 # Replay from beginning of log so buffs applied before encounter start remain tracked.
 for e in events:
  t=e['t']
  if t>end:break
  if e['k'] not in aura_events:continue
  if e['aura'] not in ('BUFF','DEBUFF'):continue
  if actor!='all' and e['d']!=actor:continue
  if target!='all' and e['d']!=target:continue
  key=(e['d'],e['dn'],e['sid'],e['spell'],e['aura'])
  kind=e['k']
  if kind in ('SPELL_AURA_APPLIED','SPELL_AURA_REFRESH','SPELL_AURA_APPLIED_DOSE'):
   if key not in states:states[key]=t
  elif kind in ('SPELL_AURA_REMOVED','SPELL_AURA_BROKEN','SPELL_AURA_BROKEN_SPELL','SPELL_AURA_REMOVED_DOSE'):
   if kind=='SPELL_AURA_REMOVED_DOSE' and e['stacks']>0:continue
   if key in states:
    began=states.pop(key)
    a=max(start,began);b=min(end,t)
    if b>a:
     totals[key]=totals.get(key,0)+(b-a)
     intervals.setdefault(key,[]).append([round(a-start,2),round(b-start,2)])
 for key,began in states.items():
  a=max(start,began)
  if end>a:
   totals[key]=totals.get(key,0)+(end-a)
   intervals.setdefault(key,[]).append([round(a-start,2),round(end-start,2)])
 rows=[]
 for key,secs in totals.items():
  guid,name,sid,spell,aura=key
  rows.append({'targetId':guid,'target':name,'spellId':sid,'spell':spell,'type':aura,'seconds':round(secs,2),'percent':round(min(100,secs/duration*100),2),'intervals':intervals.get(key,[])})
 rows.sort(key=lambda r:(-r['seconds'],r['target'],r['spell']))
 return rows

# Explicitly identified WotLK dual-wield effect IDs. Never infer relationships by name alone.
SPELL_RELATIONS = {
  66962: (55268, 'Off-hand'), 66216: (49921, 'Off-hand'),
  66217: (56815, 'Off-hand'), 66953: (49924, 'Off-hand'),
}
SPELL_OVERRIDES_PATH = ROOT / 'spell_overrides.json'
def spell_overrides():
 try:
  value=json.loads(SPELL_OVERRIDES_PATH.read_text(encoding='utf-8'))
  return value if isinstance(value,dict) else {}
 except (OSError, ValueError):return {}

def spell_identity(spell_id, name, overrides):
 override=overrides.get(str(spell_id),{})
 if not isinstance(override,dict):override={}
 parent,role=SPELL_RELATIONS.get(spell_id,(spell_id,'Primary'))
 if override.get('parentId') is not None:
  try:parent=int(override['parentId'])
  except (ValueError,TypeError):pass
 role=str(override.get('role',role))
 return parent,role,str(override.get('name',name))

def report(q):
 with LOCK: data=DATA
 ev=data['events'];segs=data['segments'];idx=number(q.get('segment',['-1'])[0]); actor=q.get('actor',['all'])[0];metric=q.get('metric',['damage'])[0]; target=q.get('target',['all'])[0]
 if 0<=idx<len(segs):start=segs[idx]['start'];end=segs[idx]['end']
 elif ev:start=ev[0]['t'];end=ev[-1]['t']
 else:start=end=0
 duration=max(1,sum(seg['duration'] for seg in segs)) if idx==-1 and segs else max(1,end-start)
 kindset={'damage':('DAMAGE',),'healing':('HEAL',),'taken':('DAMAGE',)}
 def valid(e):
  if not(start<=e['t']<=end):return False
  if target!='all' and e['d']!=target:return False
  if metric=='damage':return e['amount']>0 and 'DAMAGE' in e['k']
  if metric=='healing':return e['amount']>0 and 'HEAL' in e['k']
  return e['amount']>0 and 'DAMAGE' in e['k']
 selected=[e for e in ev if valid(e) and (idx!=-1 or not segs or any(seg['start']<=e['t']<=seg['end'] for seg in segs))]
 owners=data.get('owners',{})
 def attributed(guid):
  if metric=='taken':return guid
  seen=set()
  while guid in owners and guid not in seen:
   seen.add(guid);guid=owners[guid]
  return guid
 names={a['id']:a['name'] for a in data['actors']}
 players={a['id'] for a in data['actors'] if a['player']}
 totals=defaultdict(lambda:{'amount':0,'hits':0,'crits':0,'over':0,'absorb':0,'pets':defaultdict(int)})
 for e in selected:
  rawguid=e['d'] if metric=='taken' else e['s'];guid=attributed(rawguid)
  # Damage Done is a PLAYER leaderboard: never create pet, guardian,
  # NPC, or training-dummy rows. Only verified owner mappings roll up.
  if metric=='damage' and guid not in players:continue
  name=names.get(guid) or (e['dn'] if metric=='taken' else e['sn']);key=(guid,name)
  a=totals[key];v=max(0,e['amount']-e['over']) if metric=='healing' else e['amount'];a['amount']+=v;a['hits']+=1;a['crits']+=int(e['crit']);a['over']+=e['over'];a['absorb']+=e['absorb'];
  if rawguid!=guid:a['pets'][e['sn'] or rawguid]+=v
 ranks=[{'id':k[0],'name':k[1] or 'Unknown',**{**v,'pets':dict(v['pets'])},'rate':round(v['amount']/duration,1)} for k,v in totals.items()]
 ranks.sort(key=lambda x:x['amount'],reverse=True)
 chosen=[e for e in selected if (metric!='damage' or attributed(e['s']) in players) and (actor=='all' or attributed(e['d'] if metric=='taken' else e['s'])==actor)]
 spells=defaultdict(lambda:{'amount':0,'hits':0,'crits':0,'over':0,'max':0,'min':None,'critAmount':0,'critHits':0,'normalAmount':0,'normalHits':0})
 timeline=defaultdict(int)
 for e in chosen:
  v=max(0,e['amount']-e['over']) if metric=='healing' else e['amount'];a=spells[(e['sid'],e['spell'])];a['amount']+=v;a['hits']+=1;a['crits']+=int(e['crit']);a['over']+=e['over'];a['max']=max(a['max'],v);a['min']=v if a['min'] is None else min(a['min'],v)
  if e['crit']:a['critAmount']+=v;a['critHits']+=1
  else:a['normalAmount']+=v;a['normalHits']+=1
  timeline[int(e['t']-start)]+=v
 overrides=spell_overrides()
 abilities=[]
 for (sid,name),v in spells.items():
  parent,role,display=spell_identity(sid,name,overrides)
  abilities.append({'id':sid,'name':display,'parentId':parent,'role':role,**v,'avg':round(v['amount']/v['hits'],2) if v['hits'] else 0,'avgCrit':round(v['critAmount']/v['critHits'],2) if v['critHits'] else None,'avgNormal':round(v['normalAmount']/v['normalHits'],2) if v['normalHits'] else None})
 abilities.sort(key=lambda x:x['amount'],reverse=True)
 # Parent/child grouping is metadata only: no damage events are duplicated or removed.
 groups={}
 for a in abilities:
  key=a['parentId'] if a['parentId']!=a['id'] else a['id']
  group=groups.setdefault(key,{'parentId':key,'name':a['name'],'amount':0,'hits':0,'crits':0,'critAmount':0,'critHits':0,'min':None,'max':0,'components':[]})
  group['components'].append(a)
  for field in ('amount','hits','crits','critAmount','critHits'):group[field]+=a[field]
  group['min']=a['min'] if group['min'] is None else min(group['min'],a['min'])
  group['max']=max(group['max'],a['max'])
 for group in groups.values():
  primary=next((a for a in group['components'] if a['id']==group['parentId']),None)
  if primary:group['name']=primary['name']
  group['avg']=round(group['amount']/group['hits'],2) if group['hits'] else 0
  group['avgCrit']=round(group['critAmount']/group['critHits'],2) if group['critHits'] else None
 grouped_abilities=sorted(groups.values(),key=lambda g:g['amount'],reverse=True)
 # include zero-value cast/aura/death events, limited for browser payload
 detail=[e for e in ev if start<=e['t']<=end and (actor=='all' or attributed(e['s'])==actor or e['d']==actor) and (target=='all' or e['d']==target)]
 deaths=[e for e in detail if e['k'] in ('UNIT_DIED','UNIT_DESTROYED','PARTY_KILL')]
 casts=[e for e in detail if e['k'] in ('SPELL_CAST_SUCCESS','SPELL_CAST_FAILED')]
 auras=[e for e in detail if 'AURA_' in e['k']]
 points=sorted(timeline.items());limit=1800
 if len(points)>limit:
  step=max(1,int(duration/limit));b=defaultdict(int)
  for sec,v in points:b[(sec//step)*step]+=v
  points=sorted(b.items())
 return {'meta':data['meta'],'segments':segs,'actors':data['actors'],'start':start,'end':end,'duration':duration,'ranking':ranks,'abilities':abilities[:200],'abilityGroups':grouped_abilities[:200],'timeline':points,'summary':{'total':sum(e['amount']-e['over'] if metric=='healing' else e['amount'] for e in chosen),'events':len(chosen),'deaths':len(deaths),'casts':len(casts),'auras':len(auras)},'deaths':deaths[:300],'casts':casts[:800],'auras':auras[:800],'events':detail[:1200],'buffUptime':buff_uptime(ev,start,end,actor,target),'fightRoster':gear_for_fight(data,idx) if 0<=idx<len(segs) else []}
def enemy_report(q):
 """Enemy-focused statistics for observed 3.3.5a events, without player-only filtering."""
 with LOCK:data=DATA
 segments=data['segments'];events=data['events'];idx=number(q.get('segment',['-1'])[0]);target=q.get('enemy',['all'])[0]
 if 0<=idx<len(segments):ranges=[segments[idx]]
 else:ranges=segments
 def in_combat(e):return any(seg['start']<=e['t']<=seg['end'] for seg in ranges)
 actors={a['id']:a for a in data['actors']};owners=data.get('owners',{})
 def enemy(guid):
  a=actors.get(guid)
  return bool(a and not a['player'] and guid not in owners and not (a['flags']&0x3000))
 rows={}
 for e in events:
  if not in_combat(e):continue
  is_damage='DAMAGE' in e['k'] and e['amount']>0
  is_heal='HEAL' in e['k'] and e['amount']>0
  if not (is_damage or is_heal):continue
  for guid,direction in ((e['s'],'outgoing'),(e['d'],'incoming')):
   if not enemy(guid) or (target!='all' and guid!=target):continue
   row=rows.setdefault(guid,{'id':guid,'name':actors[guid]['name'],'damageDone':0,'damageTaken':0,'healingDone':0,'healingReceived':0,'abilities':{},'targets':{},'events':0})
   row['events']+=1
   value=e['amount']
   field=('damageDone' if direction=='outgoing' else 'damageTaken') if is_damage else ('healingDone' if direction=='outgoing' else 'healingReceived')
   if is_heal:value=max(0,value-e['over'])
   row[field]+=value
   if direction=='outgoing':
    key=str(e['sid'])+'|'+e['spell']+'|'+e['k']
    a=row['abilities'].setdefault(key,{'id':e['sid'],'name':e['spell'],'eventType':e['k'],'amount':0,'hits':0,'crits':0,'min':None,'max':0})
    a['amount']+=value;a['hits']+=1;a['crits']+=int(e['crit']);a['min']=value if a['min'] is None else min(a['min'],value);a['max']=max(a['max'],value)
    t=row['targets'].setdefault(e['d'],{'id':e['d'],'name':e['dn'],'damage':0,'healing':0})
    t['damage' if is_damage else 'healing']+=value
 output=[]
 for row in rows.values():
  row['abilities']=sorted(({**a,'avg':round(a['amount']/a['hits'],2)} for a in row['abilities'].values()),key=lambda a:a['amount'],reverse=True)
  row['targets']=sorted(row['targets'].values(),key=lambda t:t['damage']+t['healing'],reverse=True)
  output.append(row)
 output.sort(key=lambda a:a['damageDone'],reverse=True)
 return {'enemies':output,'segments':segments,'meta':data['meta'],'note':'Client-observed values only. Enemy detection uses combat-log flags; some custom units may require overrides.'}

def import_background(path, uploaded=False, display_name=None):
 global ACTIVE_LOG
 try:
  def progress(lines, ignored):
   with IMPORT_LOCK:IMPORT_STATE['linesRead']=lines
  parsed=parse(path,progress)
  if display_name:parsed['meta']['filename']=display_name
  with LOCK:
   DATA.update(parsed)
   ACTIVE_LOG=None if uploaded else path
  with IMPORT_LOCK:
   IMPORT_STATE.update(state='complete',message='Import complete',finished=time.time(),linesRead=parsed['meta'].get('parsed',0))
  if not uploaded:
   try:WATCH_STATE['lastSignature']=(path.stat().st_size,path.stat().st_mtime_ns)
   except OSError:pass
 except Exception as exc:
  with IMPORT_LOCK:IMPORT_STATE.update(state='error',message=str(exc),finished=time.time())
  print('Import error:',repr(exc),flush=True)
 finally:
  if uploaded:
   try:path.unlink(missing_ok=True)
   except OSError:pass

def start_import(path,uploaded=False,display_name=None):
 with IMPORT_LOCK:
  if IMPORT_STATE['state']=='running':return False
  IMPORT_STATE.update(state='running',message='Parsing combat log',started=time.time(),finished=0,linesRead=0,bytesTotal=path.stat().st_size,bytesRead=0)
 threading.Thread(target=import_background,args=(path,uploaded,display_name),daemon=True).start()
 return True

def watch_combat_log():
 while True:
  time.sleep(WATCH_STATE['interval'])
  if not WATCH_STATE['enabled'] or not ACTIVE_LOG:continue
  try:
   path=ACTIVE_LOG
   signature=(path.stat().st_size,path.stat().st_mtime_ns)
   if WATCH_STATE['lastSignature'] is None:
    WATCH_STATE['lastSignature']=signature
   elif signature!=WATCH_STATE['lastSignature']:
    # Reparse on change; full incremental event indexing is not yet implemented.
    if start_import(path):WATCH_STATE['lastSignature']=signature
  except OSError:pass

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,data,status=200,mime='application/json'):
  raw=json.dumps(data,separators=(',',':')).encode();self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  url=urlparse(self.path)
  if url.path=='/api/report':return self.send(report(parse_qs(url.query)))
  if url.path=='/api/enemies':return self.send(enemy_report(parse_qs(url.query)))
  if url.path=='/api/status':return self.send({**DATA['meta'],'activePath':str(ACTIVE_LOG) if ACTIVE_LOG else '','import':dict(IMPORT_STATE),'watching':WATCH_STATE['enabled']})
  if url.path=='/api/import/status':return self.send(dict(IMPORT_STATE))
  if url.path=='/api/profiles':return self.send({'profiles':list(PROFILES.values()),'historyCount':len(GEAR_HISTORY)})
  if url.path=='/api/gear-history':return self.send({'snapshots':GEAR_HISTORY})
  if url.path in ('/','/index.html'):
   raw=(ROOT/'web'/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();return self.wfile.write(raw)
  self.send({'error':'not found'},404)
 def do_POST(self):
  global ACTIVE_LOG
  if self.path=='/api/watch':
   WATCH_STATE['enabled']=not WATCH_STATE['enabled'];return self.send({'watching':WATCH_STATE['enabled']})
  if self.path=='/api/log/clear':
   with LOCK:
    DATA.clear();DATA.update({'events':[],'segments':[],'actors':[],'meta':{'filename':'No log loaded','parsed':0,'segments':0}})
    ACTIVE_LOG=None
   return self.send({'cleared':True})
  if self.path=='/api/log/delete':
   # Destructive deletion is only permitted for an explicitly selected local log.
   with LOCK:
    target=ACTIVE_LOG
   if not target:return self.send({'error':'No local combat log selected for deletion'},400)
   try:
    if target.name.lower()!='wowcombatlog.txt':return self.send({'error':'Only WoWCombatLog.txt can be deleted'},400)
    target.unlink()
    with LOCK:
     DATA.clear();DATA.update({'events':[],'segments':[],'actors':[],'meta':{'filename':'No log loaded','parsed':0,'segments':0}})
     ACTIVE_LOG=None
    return self.send({'deleted':True,'filename':target.name})
   except OSError as exc:return self.send({'error':str(exc)},500)
  if self.path=='/api/import/upload':
   n=int(self.headers.get('Content-Length','0'))
   if n<=0 or n>300_000_000:return self.send({'error':'File must be 1 byte to 300 MB'},413)
   import tempfile
   tmp=None
   try:
    with tempfile.NamedTemporaryFile(mode='wb',suffix='.txt',delete=False) as f:
     tmp=Path(f.name)
     remaining=n
     while remaining:
      chunk=self.rfile.read(min(1024*1024,remaining))
      if not chunk:raise ValueError('Upload incomplete')
      f.write(chunk);remaining-=len(chunk)
    if not start_import(tmp,True,self.headers.get('X-Log-Filename','Uploaded combat log')[:180]):return self.send({'error':'An import is already running'},409)
    tmp=None  # Background worker owns the temporary file.
    return self.send({'accepted':True,'state':'running'},202)
   except Exception as exc:return self.send({'error':str(exc)},400)
   finally:
    if tmp:tmp.unlink(missing_ok=True)
  if self.path=='/api/profiles/clear':
   PROFILES.clear()
   GEAR_HISTORY.clear()
   HISTORY_PATH.unlink(missing_ok=True)
   try:
    (ROOT/'profiles.json').unlink(missing_ok=True)
   except OSError as exc:
    return self.send({'error':'Could not delete cached profiles: '+str(exc)},500)
   return self.send({'cleared':True,'profiles':0})
  if self.path=='/api/profile':
   try:
    n=int(self.headers.get('Content-Length','0'))
    if n>5_000_000:return self.send({'error':'Snapshot too large'},413)
    raw=self.rfile.read(n).decode('utf-8-sig',errors='replace')
    payload=extract_snapshot_payload(raw)
    blocks=[b.strip() for b in payload.split('HCS_END') if any(line.startswith('HCS1|') for line in b.splitlines())]
    if not blocks:blocks=[payload]
    profiles=[parse_snapshot(b) for b in blocks]
    with LOCK:new=store_gear_profiles(profiles)
    profile={'imported':len(profiles),'historicalAdded':new,'names':[p['name'] for p in profiles]}
    (ROOT/'profiles.json').write_text(json.dumps(PROFILES,indent=2),encoding='utf-8')
    return self.send(profile)
   except Exception as exc:return self.send({'error':str(exc)},400)
  if self.path!='/api/import':return self.send({'error':'not found'},404)
  n=int(self.headers.get('Content-Length','0'))
  if n>300_000_000:return self.send({'error':'Max 300MB'},413)
  body=self.rfile.read(n)
  try:
   payload=json.loads(body);path=Path(payload['path']).expanduser().resolve()
   if not path.is_file():return self.send({'error':'File not found'},400)
   if not start_import(path):return self.send({'error':'An import is already running'},409)
   return self.send({'accepted':True,'state':'running'},202)
  except Exception as exc:return self.send({'error':str(exc)},400)
if HISTORY_PATH.exists():
 try:GEAR_HISTORY.extend(json.loads(HISTORY_PATH.read_text(encoding='utf-8')))
 except Exception:pass
if (ROOT/'profiles.json').exists():
 try:PROFILES.update(json.loads((ROOT/'profiles.json').read_text(encoding='utf-8')))
 except Exception:pass
if __name__=='__main__':
 if LOG.exists():
  print('Parsing sample combat log...');DATA.update(parse(LOG));ACTIVE_LOG=LOG;print(DATA['meta'])
 else:print('No bundled log; use Import to select a local path.')
 threading.Thread(target=watch_saved_snapshots,daemon=True).start()
 threading.Thread(target=watch_combat_log,daemon=True).start()
 server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
 print('Open http://127.0.0.1:8765')
 if '--no-browser' not in sys.argv:threading.Timer(1,lambda:webbrowser.open('http://127.0.0.1:8765')).start()
 try:server.serve_forever()
 except KeyboardInterrupt:pass

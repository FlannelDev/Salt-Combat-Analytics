-- Heroes WoW 3.3.5a: local/group equipment and talent snapshots.
HeroesCombatSnapshotDB = HeroesCombatSnapshotDB or {}
local DB=HeroesCombatSnapshotDB
DB.members=DB.members or {}
DB.gearHistory=DB.gearHistory or {}
local HISTORY_LIMIT=1500
local function enc(s) return (tostring(s or ''):gsub('%%','%%25'):gsub('|','%%7C'):gsub('\r',''):gsub('\n','%%0A')) end
local function say(s) DEFAULT_CHAT_FRAME:AddMessage('|cff6db9ffHCS|r '..s) end
-- Capture tooltip text from the actual Heroes WoW item. A remote inventory
-- tooltip may be empty or incomplete; hyperlink-based fallback is essential.
local tip=CreateFrame('GameTooltip','HCSInspectTooltip',UIParent,'GameTooltipTemplate')
tip:SetOwner(UIParent,'ANCHOR_NONE')
local function readTip()
 local lines={}
 for i=1,tip:NumLines() do
  local left=_G['HCSInspectTooltipTextLeft'..i]
  local right=_G['HCSInspectTooltipTextRight'..i]
  local l=left and left:GetText()
  local r=right and right:GetText()
  if l and l~='' then table.insert(lines,l) end
  if r and r~='' then table.insert(lines,r) end
 end
 return lines
end
-- Heroes WoW gear designation is the item FLAVOR TEXT enclosed in quotes.
-- Do not infer a tier from set bonuses, item names or other tooltip lines.
local function quotedFlavor(lines)
 for _,line in ipairs(lines) do
  local clean=tostring(line):gsub('|c%x%x%x%x%x%x%x%x',''):gsub('|r','')
  local flavor=clean:match('"([^"\n]+)"')
  if flavor then
   flavor=flavor:match('^%s*(.-)%s*$')
   if flavor~='' then return flavor end
  end
 end
 return nil
end
local function tooltipLines(unit,slot,link)
 local inventory,hyperlink={},{}
 -- Inventory context is preferred: it is closest to the in-game inspect tooltip.
 tip:ClearLines()
 local ok=pcall(function() tip:SetInventoryItem(unit,slot) end)
 if ok then inventory=readTip() end
 if link then
  tip:ClearLines()
  local linkOk=pcall(function() tip:SetHyperlink(link) end)
  if linkOk then hyperlink=readTip() end
 end
 -- A hyperlink tooltip can omit server-generated flavor; check both.
 return (#inventory>0 and inventory or hyperlink), quotedFlavor(inventory) or quotedFlavor(hyperlink)
end
-- Preserve tooltip flavor only when the equipped link is identical to the previous capture.
-- This prevents periodic refreshes from erasing previously confirmed tier text.
local function previousTiers(payload)
 local links,tiers,levels={},{},{}
 if not payload then return links,tiers end
 for line in tostring(payload):gmatch('[^\n]+') do
  local slot,link=line:match('^GEAR|(%d+)|(.+)$')
  if slot then links[tonumber(slot)]=link end
  local tslot,tier=line:match('^TIER|(%d+)|(.+)$')
  if tslot then tiers[tonumber(tslot)]=tier end
  local islot,ilvl=line:match('^ILVL|(%d+)|(%d+)$')
  if islot then levels[tonumber(islot)]=tonumber(ilvl) end
 end
 return links,tiers,levels
end
local function capture(unit,inspected)
 if not UnitExists(unit) then return nil,0,'unit missing' end
 if not UnitIsPlayer(unit) then return nil,0,'unit not player' end
 local name=UnitName(unit);if not name then return nil,0,'name missing' end
 local _,class=UnitClass(unit)
 local oldLinks,oldTiers,oldLevels=previousTiers(DB.members[name])
 local gearCount=0
 local lines={'HCS1|'..enc(name)..'|'..enc(GetRealmName())..'|'..enc(class)..'|'..(UnitLevel(unit) or 0)}
 table.insert(lines,'META|'..(inspected and 'INSPECT' or 'SELF')..'|'..date('%Y-%m-%d %H:%M:%S'))
 for slot=1,19 do
  local link=GetInventoryItemLink(unit,slot)
  if link then
   gearCount=gearCount+1
   local itemName, _, rarity, itemLevel, _, _, _, _, equipLoc = GetItemInfo(link)
   -- Cache a client-reported item level; custom items may be uncached or report nil.
   if type(itemLevel)=='number' and itemLevel>0 then
    table.insert(lines,'ILVL|'..slot..'|'..math.floor(itemLevel))
   elseif oldLinks[slot]==enc(link) and oldLevels[slot] then
    table.insert(lines,'ILVL|'..slot..'|'..oldLevels[slot])
   end
   if rarity and equipLoc and equipLoc~='' then table.insert(lines,'ITEMMETA|'..slot..'|'..math.floor(rarity)..'|'..enc(equipLoc)) end
   local tooltips,flavor=tooltipLines(unit,slot,link)
   if not itemName or itemName=='' then itemName=tooltips[1] end
   table.insert(lines,'GEAR|'..slot..'|'..enc(link))
   if itemName and itemName~='' then table.insert(lines,'ITEMNAME|'..slot..'|'..enc(itemName)) end
   if flavor then
    table.insert(lines,'TIER|'..slot..'|'..enc(flavor))
   elseif oldLinks[slot]==enc(link) and oldTiers[slot] then
    table.insert(lines,'TIER|'..slot..'|'..oldTiers[slot])
   end
  end
 end
 if inspected and gearCount==0 then return nil,0,'no inspect gear links available' end
 local payload=table.concat(lines,'\n')
 -- Save changes as an append-only session history. Identical gear does not need a new record.
 local history=DB.gearHistory
 local previous=nil
 for i=#history,1,-1 do if history[i].name==name then previous=history[i]; break end end
 local gearSignature=table.concat(lines,'\n'):gsub('META|[^\n]*\n','')
 if not previous or previous.signature~=gearSignature then
  table.insert(history,{name=name,capturedAt=date('%Y-%m-%d %H:%M:%S'),payload=payload,signature=gearSignature})
  if #history>HISTORY_LIMIT then table.remove(history,1) end
 end
 DB.members[name]=payload
 if not inspected then DB.snapshot=payload end
 DB.savedAt=date('%Y-%m-%d %H:%M:%S')
 return payload,gearCount,'stored'
end
refreshExport=function()
 local names={}; for name in pairs(DB.members) do table.insert(names,name) end; table.sort(names)
 local blocks={}; for _,name in ipairs(names) do table.insert(blocks,DB.members[name]) end
 DB.groupExport=table.concat(blocks,'\nHCS_END\n')
end
local queue,queued,pending={}, {},nil
local lastCaptured={}
local nextInspect=0
local diagnostics={attempts=0,success=0,timeout=0,notInspectable=0,missing=0,failed=0,last="none"}
local PATCH_VERSION="fight-history-2"
local AUTO_RESCAN_SECONDS=5
local AUTO_SELF_SECONDS=30
local function add(unit)
 if not UnitExists(unit) or not UnitIsPlayer(unit) or UnitIsUnit(unit,'player') then return end
 local guid=UnitGUID(unit); if not guid or queued[guid] or (pending and pending.guid==guid) then return end
 if lastCaptured[guid] and GetTime()-lastCaptured[guid]<AUTO_RESCAN_SECONDS then return end
 queued[guid]=true; table.insert(queue,{guid=guid,name=UnitName(unit)})
end
local function scan()
 if GetNumRaidMembers()>0 then for i=1,GetNumRaidMembers() do add('raid'..i) end
 else for i=1,GetNumPartyMembers() do add('party'..i) end end
end
local function findUnit(guid)
 local n=GetNumRaidMembers(); if n>0 then for i=1,n do local u='raid'..i; if UnitGUID(u)==guid then return u end end
 else for i=1,GetNumPartyMembers() do local u='party'..i; if UnitGUID(u)==guid then return u end end end
end
local function pump()
 if pending or GetTime()<nextInspect then return end
 while #queue>0 do
  local item=table.remove(queue,1); queued[item.guid]=nil
  local unit=findUnit(item.guid)
  if not unit then
   diagnostics.missing=diagnostics.missing+1
   diagnostics.last=item.name..': missing from roster'
  elseif not CanInspect(unit) then
   diagnostics.notInspectable=diagnostics.notInspectable+1
   diagnostics.last=item.name..': CanInspect false (range/visibility)'
  else
   pending={guid=item.guid,name=item.name,started=GetTime()}
   diagnostics.attempts=diagnostics.attempts+1
   diagnostics.last=item.name..': NotifyInspect sent'
   nextInspect=GetTime()+2.0
   NotifyInspect(unit)
   return
  end
 end
end
-- HeroesWoW 3.3.5a: LoggingCombat() returns 1 when enabled, nil when disabled.
-- LoggingCombat(true) enables logging; do not toggle with /combatlog.
local function ensureCombatLogging()
 if type(LoggingCombat)~='function' then return false end
 local ok, active=pcall(LoggingCombat)
 if ok and active then return true end
 local enabled=pcall(LoggingCombat,true)
 if not enabled then return false end
 local checked, result=pcall(LoggingCombat)
 return checked and not not result
end
local frame=CreateFrame('Frame')
frame:RegisterEvent('PLAYER_ENTERING_WORLD'); frame:RegisterEvent('PLAYER_LOGIN'); frame:RegisterEvent('PLAYER_EQUIPMENT_CHANGED'); frame:RegisterEvent('PLAYER_LOGOUT'); frame:RegisterEvent('UNIT_INVENTORY_CHANGED')
frame:RegisterEvent('PARTY_MEMBERS_CHANGED'); frame:RegisterEvent('RAID_ROSTER_UPDATE'); frame:RegisterEvent('INSPECT_TALENT_READY')
frame:SetScript('OnEvent',function(self,event,...)
 if event=='INSPECT_TALENT_READY' then
  if pending then
   local unit=findUnit(pending.guid)
   if unit then
     local ok,payload,count,reason=pcall(capture,unit,true)
     if ok and payload and count and count>0 and DB.members[pending.name]==payload then
      lastCaptured[pending.guid]=GetTime()
      refreshExport()
      diagnostics.success=diagnostics.success+1
      diagnostics.last=pending.name..': STORED '..count..' slots at '..tostring(DB.savedAt)
     else
      diagnostics.failed=diagnostics.failed+1
      diagnostics.last=pending.name..': capture FAILED ('..tostring(ok and reason or payload)..')'
      -- Do not discard cached gear; retry at the next roster scan.
      lastCaptured[pending.guid]=GetTime()-AUTO_RESCAN_SECONDS+1
     end
    else diagnostics.missing=diagnostics.missing+1; diagnostics.last=pending.name..': ready but unit missing' end
   if ClearInspectPlayer then ClearInspectPlayer() end
   pending=nil
  end
 elseif event=='PLAYER_ENTERING_WORLD' then ensureCombatLogging()
 elseif event=='PLAYER_LOGIN' then ensureCombatLogging(); capture('player',false); scan(); refreshExport(); say('Automatic group gear capture '..PATCH_VERSION..' enabled. Files update on logout/reload.')
 elseif event=='PLAYER_LOGOUT' then capture('player',false); refreshExport()
 elseif event=='PLAYER_EQUIPMENT_CHANGED' then capture('player',false); refreshExport()
 elseif event=='UNIT_INVENTORY_CHANGED' then local unit=...; if unit=='player' then capture('player',false); refreshExport() else scan() end
 else scan() end
end)
local elapsed=0
local rescanElapsed=0
local selfElapsed=0
local logCheckElapsed=0
frame:SetScript('OnUpdate',function(self,dt)
 elapsed=elapsed+dt; rescanElapsed=rescanElapsed+dt; selfElapsed=selfElapsed+dt; logCheckElapsed=logCheckElapsed+dt
 if logCheckElapsed>=10 then logCheckElapsed=0; ensureCombatLogging() end
 if elapsed<0.5 then return end; elapsed=0
 if rescanElapsed>=5 then rescanElapsed=0; scan() end
 if selfElapsed>=AUTO_SELF_SECONDS then selfElapsed=0; capture('player',false); refreshExport() end
 if pending and GetTime()-pending.started>5 then diagnostics.timeout=diagnostics.timeout+1; diagnostics.last=pending.name..': timed out waiting for INSPECT_TALENT_READY'; pending=nil; if ClearInspectPlayer then ClearInspectPlayer() end end
 pump()
end)
SLASH_HEROESCOMBATSNAPSHOT1='/hcs'
SlashCmdList.HEROESCOMBATSNAPSHOT=function(msg)
 msg=(msg or ''):lower():match('^%s*(.-)%s*$')
 if msg=='log' then say('Disk combat logging: '..(type(LoggingCombat)=='function' and (LoggingCombat() and 'ON' or 'OFF') or 'status unavailable'))
 elseif msg=='scan' then scan(); say('Group inspection queued. Stand near party/raid members; inspections are throttled.')
 elseif msg=='save' or msg=='' then local payload,count,reason=capture('player',false); scan(); refreshExport(); say('Self snapshot '..tostring(reason)..' ('..tostring(count)..' slots). DB savedAt='..tostring(DB.savedAt)..'. WoW writes file on logout/reload.')
 elseif msg=='status' or msg=='debug' then local n=0; for _ in pairs(DB.members) do n=n+1 end; say(n..' characters cached; '..#queue..' queued; '..(pending and pending.name or 'no active inspect')); say('Inspect: sent='..diagnostics.attempts..' success='..diagnostics.success..' timeout='..diagnostics.timeout..' rejected='..diagnostics.notInspectable..' missing='..diagnostics.missing..' failed='..diagnostics.failed); say('Last: '..diagnostics.last); say('DB savedAt='..tostring(DB.savedAt)..' | Flandk='..tostring(DB.members.Flandk and DB.members.Flandk:match('META|INSPECT|([^\n]+)') or 'none')..' | '..PATCH_VERSION)
 elseif msg=='clear' then DB.members={}; DB.gearHistory={}; capture('player',false); refreshExport(); say('Cleared cached members.')

 else say('Automatic capture is active. Optional: /hcs log, /hcs save, /hcs scan, /hcs status, /hcs clear') end
end

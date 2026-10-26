-- Salt Combat Analytics: compact in-game HCS interface for WoW 3.3.5a.
-- Uses client-observed combat events; desktop application remains authoritative for reports.
local db = HeroesCombatSnapshotDB
if not db then db = {}; HeroesCombatSnapshotDB = db end
local state = {damage=0, healing=0, started=nil, elapsed=0, inCombat=false}
local function fmt(v)
 v=tonumber(v) or 0
 if v>=1000000000 then return string.format('%.2fB',v/1000000000) end
 if v>=1000000 then return string.format('%.2fM',v/1000000) end
 if v>=1000 then return string.format('%.1fK',v/1000) end
 return tostring(math.floor(v))
end
local ui=CreateFrame('Frame','HCSStatusWindow',UIParent)
ui:SetWidth(330); ui:SetHeight(338)
ui:SetFrameStrata('DIALOG'); ui:SetMovable(true); ui:EnableMouse(true)
ui:RegisterForDrag('LeftButton')
ui:SetScript('OnDragStart',function(self) self:StartMoving() end)
ui:SetScript('OnDragStop',function(self)
 self:StopMovingOrSizing()
 local point,_,relativePoint,x,y=self:GetPoint(1)
 db.uiPosition={point=point,relativePoint=relativePoint,x=x,y=y}
end)
ui:SetClampedToScreen(true)
local pos=db.uiPosition
if pos and pos.point then ui:SetPoint(pos.point,UIParent,pos.relativePoint or pos.point,pos.x or 0,pos.y or 0)
else ui:SetPoint('CENTER',UIParent,'CENTER',0,0) end
ui:SetBackdrop({bgFile='Interface\\DialogFrame\\UI-DialogBox-Background',edgeFile='Interface\\DialogFrame\\UI-DialogBox-Border',tile=true,tileSize=32,edgeSize=24,insets={left=8,right=8,top=8,bottom=8}})
local function label(text,x,y,size,r,g,b)
 local f=ui:CreateFontString(nil,'OVERLAY','GameFontNormal')
 f:SetPoint('TOPLEFT',ui,'TOPLEFT',x,y); f:SetFont('Fonts\\FRIZQT__.TTF',size or 12,'OUTLINE')
 f:SetTextColor(r or 1,g or 1,b or 1); f:SetText(text); return f
end
label('HCS  |  SALT COMBAT ANALYTICS',18,-18,12,1,.75,.42)
label('By Flannel  •  WoW 3.3.5a',18,-38,10,.75,.7,.7)
local close=CreateFrame('Button',nil,ui,'UIPanelCloseButton'); close:SetPoint('TOPRIGHT',ui,'TOPRIGHT',-4,-4)
local logging=label('Combat logging: checking...',18,-65,12)
local damage=label('Damage Done: 0',18,-92,12)
local dps=label('DPS: 0',18,-114,12)
local healing=label('Healing Done: 0',18,-136,12)
local hps=label('HPS: 0',18,-158,12)
local gear=label('Gear snapshot: checking...',18,-180,11,.9,.8,.55)
local group=label('Group cache: checking...',18,-200,11,.9,.8,.55)
local feedback=label('Commands are also available via /hcs',18,-222,10,.7,.7,.7)
local function button(text,x,y,fn)
 local b=CreateFrame('Button',nil,ui,'UIPanelButtonTemplate')
 b:SetWidth(142); b:SetHeight(23); b:SetPoint('TOPLEFT',ui,'TOPLEFT',x,y)
 b:SetText(text); b:SetScript('OnClick',fn); return b
end
local function runCommand(cmd)
 local handler=SlashCmdList and SlashCmdList.HEROESCOMBATSNAPSHOT
 if handler then handler(cmd) end
end
local function message(s)
 feedback:SetText(s)
end
local function reset()
 state.damage=0;state.healing=0;state.started=nil;state.elapsed=0
 state.inCombat=UnitAffectingCombat('player') and true or false
 if state.inCombat then state.started=GetTime() end
 message('Local combat counters reset')
end
button('Save Gear',17,-247,function()
 runCommand('save');message('Gear snapshot requested')
end)
button('Scan Group',170,-247,function()
 runCommand('scan');message('Group inspection queued')
end)
button('Inspect Status',17,-274,function()
 runCommand('status');message('Inspection details sent to chat')
end)
button('Enable Logging',170,-274,function()
 if type(LoggingCombat)~='function' then
  message('LoggingCombat API unavailable')
  return
 end
 local ok, active=pcall(LoggingCombat)
 if ok and active then
  message('Combat logging already enabled')
  return
 end
 local requested=pcall(LoggingCombat,true)
 local verified, nowActive=pcall(LoggingCombat)
 if requested and verified and nowActive then
  message('Combat logging enabled')
 else
  message('Unable to confirm combat logging enabled')
 end
end)
button('Reset Combat',17,-301,reset)
button('Clear Cache',170,-301,function()
 StaticPopup_Show('HCS_CONFIRM_CLEAR_CACHE')
end)
StaticPopupDialogs['HCS_CONFIRM_CLEAR_CACHE']={
 text='Clear HCS cached group equipment and gear history? This cannot be undone after SavedVariables are written.',
 button1=YES,button2=NO,
 OnAccept=function() runCommand('clear');message('Group cache cleared') end,
 timeout=0,whileDead=1,hideOnEscape=1,preferredIndex=3
}
local function update()
 local active=type(LoggingCombat)=='function' and LoggingCombat()
 logging:SetText('Combat Logging: '..(active and '|cff55ff88Enabled|r' or '|cffff6666Disabled|r'))
 local t=state.elapsed
 if state.inCombat and state.started then t=t+math.max(0,GetTime()-state.started) end
 damage:SetText('Damage Done: '..fmt(state.damage))
 dps:SetText('DPS: '..fmt(t>0 and state.damage/t or 0))
 healing:SetText('Healing Done: '..fmt(state.healing))
 hps:SetText('HPS: '..fmt(t>0 and state.healing/t or 0))
 local name=UnitName('player')
 local has=db.members and name and db.members[name]
 gear:SetText('Gear Snapshot: '..(has and '|cff55ff88Cached|r' or '|cffffcc66Pending|r'))
 local count=0
 if db.members then for _ in pairs(db.members) do count=count+1 end end
 group:SetText('Cached characters: '..tostring(count))
end
local events=CreateFrame('Frame')
events:RegisterEvent('COMBAT_LOG_EVENT_UNFILTERED')
events:RegisterEvent('PLAYER_REGEN_DISABLED')
events:RegisterEvent('PLAYER_REGEN_ENABLED')
events:RegisterEvent('PLAYER_ENTERING_WORLD')
events:SetScript('OnEvent',function(self,event,...)
 if event=='PLAYER_REGEN_DISABLED' then
  if not state.inCombat then state.inCombat=true;state.started=GetTime() end
 elseif event=='PLAYER_REGEN_ENABLED' then
  if state.inCombat and state.started then state.elapsed=state.elapsed+math.max(0,GetTime()-state.started) end
  state.inCombat=false;state.started=nil
 elseif event=='PLAYER_ENTERING_WORLD' then
  state.inCombat=UnitAffectingCombat('player') and true or false
  if state.inCombat and not state.started then state.started=GetTime() end
 elseif event=='COMBAT_LOG_EVENT_UNFILTERED' then
  local subevent=select(2,...)
  local srcGUID=select(3,...)
  if srcGUID~=UnitGUID('player') then return end
  local amount
  if subevent=='SWING_DAMAGE' then amount=select(9,...);state.damage=state.damage+math.max(0,tonumber(amount) or 0)
  elseif subevent=='SPELL_DAMAGE' or subevent=='RANGE_DAMAGE' or subevent=='SPELL_PERIODIC_DAMAGE' or subevent=='DAMAGE_SHIELD' or subevent=='DAMAGE_SPLIT' then
   amount=select(12,...);state.damage=state.damage+math.max(0,tonumber(amount) or 0)
  elseif subevent=='SPELL_HEAL' or subevent=='SPELL_PERIODIC_HEAL' then
   amount=select(12,...);state.healing=state.healing+math.max(0,tonumber(amount) or 0)
  end
 end
end)
local refresh=0
ui:SetScript('OnUpdate',function(self,dt) refresh=refresh+dt;if refresh>=.5 then refresh=0;update() end end)
ui:Hide()
local previous=SlashCmdList.HEROESCOMBATSNAPSHOT
SLASH_HCSWINDOW1='/hcsui'
SlashCmdList.HCSWINDOW=function() if ui:IsShown() then ui:Hide() else ui:Show();update() end end
SlashCmdList.HEROESCOMBATSNAPSHOT=function(msg)
 local command=(msg or ''):lower():match('^%s*(.-)%s*$')
 if command=='' or command=='show' or command=='ui' then
  if ui:IsShown() then ui:Hide() else ui:Show();update() end
 elseif previous then previous(msg) end
end

if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage('|cff6db9ffHCS|r UI loaded. Type /hcsui or /hcs to open the window.') end

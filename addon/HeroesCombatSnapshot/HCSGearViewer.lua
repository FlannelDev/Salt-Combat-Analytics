-- HCS Gear Viewer: reads the existing HeroesCombatSnapshotDB.members payloads.
-- Compatible with the Wrath 3.3.5a (30300) UI API.
local db = HeroesCombatSnapshotDB or {}
local selectedName
local rows = {}
local slots = {"Head","Neck","Shoulder","Shirt","Chest","Waist","Legs","Feet","Wrist","Hands","Finger 1","Finger 2","Trinket 1","Trinket 2","Back","Main Hand","Off Hand","Ranged","Tabard"}
local function decode(s)
 return (tostring(s or ''):gsub('%%0A','\n'):gsub('%%7C','|'):gsub('%%25','%%'))
end
local function parse(payload)
 local result={items={},name='',realm='',class='',level='',source='',timestamp=''}
 if type(payload)~='string' then return result end
 for line in payload:gmatch('[^\n]+') do
  local name,realm,class,level=line:match('^HCS1|([^|]*)|([^|]*)|([^|]*)|([^|]*)')
  if name then result.name=decode(name);result.realm=decode(realm);result.class=decode(class);result.level=level end
  local source,ts=line:match('^META|([^|]*)|(.+)$')
  if source then result.source=source;result.timestamp=ts end
  local slot,link=line:match('^GEAR|(%d+)|(.+)$')
  if slot then local n=tonumber(slot);result.items[n]=result.items[n] or {};result.items[n].link=decode(link) end
  local ns,itemName=line:match('^ITEMNAME|(%d+)|(.+)$')
  if ns then local n=tonumber(ns);result.items[n]=result.items[n] or {};result.items[n].name=decode(itemName) end
  local li,ilvl=line:match('^ILVL|(%d+)|(%d+)$')
  if li then local n=tonumber(li);result.items[n]=result.items[n] or {};result.items[n].ilvl=tonumber(ilvl) end
  local ms,mq,ml=line:match('^ITEMMETA|(%d+)|(%d+)|(.+)$')
  if ms then local n=tonumber(ms);result.items[n]=result.items[n] or {};result.items[n].quality=tonumber(mq);result.items[n].equipLoc=decode(ml) end
  local nt,tier=line:match('^TIER|(%d+)|(.+)$')
  if nt then local n=tonumber(nt);result.items[n]=result.items[n] or {};result.items[n].tier=decode(tier) end
 end
 return result
end
local viewer=CreateFrame('Frame','HCSGearViewer',UIParent)
viewer:SetWidth(510);viewer:SetHeight(550);viewer:SetFrameStrata('DIALOG');viewer:SetMovable(true);viewer:EnableMouse(true)
viewer:RegisterForDrag('LeftButton');viewer:SetScript('OnDragStart',function(self) self:StartMoving() end)
viewer:SetScript('OnDragStop',function(self) self:StopMovingOrSizing() end)
viewer:SetPoint('CENTER');viewer:SetClampedToScreen(true)
viewer:SetBackdrop({bgFile='Interface\\DialogFrame\\UI-DialogBox-Background',edgeFile='Interface\\DialogFrame\\UI-DialogBox-Border',tile=true,tileSize=32,edgeSize=24,insets={left=8,right=8,top=8,bottom=8}})
local function text(parent,x,y,width,value,size)
 local f=parent:CreateFontString(nil,'OVERLAY','GameFontNormal');f:SetPoint('TOPLEFT',parent,'TOPLEFT',x,y)
 f:SetWidth(width);f:SetJustifyH('LEFT');f:SetFont('Fonts\\FRIZQT__.TTF',size or 12,'OUTLINE');f:SetText(value or '');return f
end
text(viewer,18,-19,400,'HCS | INSPECTED EQUIPMENT',14)
text(viewer,18,-39,440,'Salt Combat Analytics · By Flannel',10)
local close=CreateFrame('Button',nil,viewer,'UIPanelCloseButton');close:SetPoint('TOPRIGHT',-4,-4)
local selected=text(viewer,18,-70,470,'Character: —',13)
local metadata=text(viewer,18,-91,470,'No snapshot selected',11)
local chooser=CreateFrame('Button',nil,viewer,'UIPanelButtonTemplate')
chooser:SetWidth(220);chooser:SetHeight(23);chooser:SetPoint('TOPLEFT',viewer,'TOPLEFT',18,-113)
chooser:SetText('Select cached character')
local refreshButton=CreateFrame('Button',nil,viewer,'UIPanelButtonTemplate')
refreshButton:SetWidth(110);refreshButton:SetHeight(23);refreshButton:SetPoint('TOPLEFT',viewer,'TOPLEFT',247,-113);refreshButton:SetText('Refresh')
local scanButton=CreateFrame('Button',nil,viewer,'UIPanelButtonTemplate')
scanButton:SetWidth(120);scanButton:SetHeight(23);scanButton:SetPoint('TOPLEFT',viewer,'TOPLEFT',362,-113);scanButton:SetText('Scan Group')
local scroll=CreateFrame('ScrollFrame','HCSGearScroll',viewer,'UIPanelScrollFrameTemplate')
scroll:SetPoint('TOPLEFT',viewer,'TOPLEFT',18,-146);scroll:SetPoint('BOTTOMRIGHT',viewer,'BOTTOMRIGHT',-38,40)
local content=CreateFrame('Frame',nil,scroll);content:SetWidth(445);content:SetHeight(19*31);scroll:SetScrollChild(content)
for i=1,19 do
 local b=CreateFrame('Button',nil,content);b:SetWidth(440);b:SetHeight(29);b:SetPoint('TOPLEFT',content,'TOPLEFT',0,-(i-1)*31)
 local bg=b:CreateTexture(nil,'BACKGROUND');bg:SetAllPoints(b);bg:SetTexture(0.12,0.10,0.13,0.65)
 local label=text(b,5,-5,100,slots[i] or tostring(i),10)
 local item=text(b,106,-5,325,'—',11)
 b:SetScript('OnEnter',function(self)
  if self.itemLink then GameTooltip:SetOwner(self,'ANCHOR_RIGHT');GameTooltip:SetHyperlink(self.itemLink);GameTooltip:Show() end
 end)
 b:SetScript('OnLeave',function() GameTooltip:Hide() end)
 b:SetScript('OnClick',function(self)
  if self.itemLink and IsModifiedClick('CHATLINK') and ChatEdit_InsertLink then ChatEdit_InsertLink(self.itemLink) end
 end)
 rows[i]={button=b,item=item}
end
local footer=text(viewer,18,-523,460,'Hover an item for its tooltip. Data comes from HCS SavedVariables.',10)
-- Uses GearScoreLite: Reborn's per-item quality, iLvl and inventory-type formula.
local function gearSummary(items, class)
 local sum,known,eligible=0,0,0
 for slot=1,19 do
  local item=items[slot]
  if slot~=4 and slot~=19 and item and item.link then
   eligible=eligible+1
   if item.ilvl and item.ilvl>0 then known=known+1;sum=sum+item.ilvl end
  end
 end
 local avg=known>0 and string.format('%.1f',sum/known) or 'unavailable'
 local score,scored,missing=HCS_GearScoreCalculate(items,class)
 if scored==0 then return string.format('Avg iLvl: %s (%d/%d known) | GearScore: unavailable',avg,known,eligible) end
 local suffix=missing>0 and string.format(' (partial; %d unresolved)',missing) or ''
 return string.format('Avg iLvl: %s (%d/%d known) | GearScoreLite GS: %d%s',avg,known,eligible,score,suffix)
end
local function redraw()
 local members=db.members or {}
 if not selectedName or not members[selectedName] then
  selectedName=UnitName('player')
  if not members[selectedName] then for name in pairs(members) do selectedName=name;break end end
 end
 local data=parse(selectedName and members[selectedName])
 selected:SetText('Character: '..(data.name~='' and data.name or (selectedName or 'No cached characters')))
 metadata:SetText((data.class or '')..'  Lv '..(data.level or '')..'  |  '..(data.source or '')..'  |  '..(data.timestamp or ''))
 local count=0
 for i=1,19 do
  local item=data.items[i];local row=rows[i]
  row.button.itemLink=item and item.link or nil
  if item and item.link then
   count=count+1
   local name=item.name or (item.link:match('%[(.-)%]') or 'Unknown item')
   local label=name
   if item.ilvl then label=label..'  |cffd5b57b[iLvl '..item.ilvl..']|r' end
   if item.tier and item.tier~='' then label=label..'  ('..item.tier..')' end
   row.item:SetText(label)
  else row.item:SetText('|cff777777Empty / unavailable|r') end
 end
 footer:SetText(gearSummary(data.items,data.class))
end
local menu=CreateFrame('Frame','HCSGearCharacterMenu',UIParent,'UIDropDownMenuTemplate')
chooser:SetScript('OnClick',function(self)
 local names={}
 for name in pairs(db.members or {}) do table.insert(names,name) end
 table.sort(names)
 if #names==0 then DEFAULT_CHAT_FRAME:AddMessage('|cff6db9ffHCS|r No cached characters yet. Use Scan Group.') return end
 local options={}
 for _,name in ipairs(names) do
  table.insert(options,{text=name,func=function() selectedName=name;redraw();CloseDropDownMenus() end})
 end
 EasyMenu(options,menu,self,0,0,'MENU')
end)
refreshButton:SetScript('OnClick',redraw)
scanButton:SetScript('OnClick',function()
 local cmd=SlashCmdList and SlashCmdList.HEROESCOMBATSNAPSHOT
 if cmd then cmd('scan') end
 redraw()
end)
viewer:SetScript('OnShow',redraw)
viewer:Hide()
SLASH_HCSGEAR1='/hcsgear'
SlashCmdList.HCSGEAR=function() if viewer:IsShown() then viewer:Hide() else viewer:Show() end end
local parent=_G.HCSStatusWindow
if parent then
 local open=CreateFrame('Button',nil,parent,'UIPanelButtonTemplate')
 open:SetWidth(292);open:SetHeight(22);open:SetPoint('TOPLEFT',parent,'TOPLEFT',18,-329)
 open:SetText('View Inspected Gear');open:SetScript('OnClick',function() viewer:Show() end)
 parent:SetHeight(370)
end
if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage('|cff6db9ffHCS|r Gear viewer ready: /hcsgear') end

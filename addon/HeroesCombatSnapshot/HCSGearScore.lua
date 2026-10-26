-- Adapted from the GearScoreLite: Reborn calculation supplied by the user.
-- Formula/slot modifiers preserved; enchant penalty is disabled as in its default settings.
local scale=1.8618
local mods={
 INVTYPE_RELIC=.3164,INVTYPE_TRINKET=.5625,INVTYPE_2HWEAPON=2,
 INVTYPE_WEAPONMAINHAND=1,INVTYPE_WEAPONOFFHAND=1,INVTYPE_RANGED=.3164,
 INVTYPE_THROWN=.3164,INVTYPE_RANGEDRIGHT=.3164,INVTYPE_SHIELD=1,
 INVTYPE_WEAPON=1,INVTYPE_HOLDABLE=1,INVTYPE_HEAD=1,INVTYPE_NECK=.5625,
 INVTYPE_SHOULDER=.75,INVTYPE_CHEST=1,INVTYPE_ROBE=1,INVTYPE_WAIST=.75,
 INVTYPE_LEGS=1,INVTYPE_FEET=.75,INVTYPE_WRIST=.5625,INVTYPE_HAND=.75,
 INVTYPE_FINGER=.5625,INVTYPE_CLOAK=.5625,INVTYPE_BODY=0,
}
local fallback={ [1]='INVTYPE_HEAD',[2]='INVTYPE_NECK',[3]='INVTYPE_SHOULDER',
 [5]='INVTYPE_CHEST',[6]='INVTYPE_WAIST',[7]='INVTYPE_LEGS',
 [8]='INVTYPE_FEET',[9]='INVTYPE_WRIST',[10]='INVTYPE_HAND',
 [11]='INVTYPE_FINGER',[12]='INVTYPE_FINGER',[13]='INVTYPE_TRINKET',
 [14]='INVTYPE_TRINKET',[15]='INVTYPE_CLOAK',[16]='INVTYPE_WEAPON',
 [17]='INVTYPE_WEAPONOFFHAND',[18]='INVTYPE_RANGED' }
local A={[4]={91.45,.65},[3]={81.375,.8125},[2]={73,1}}
local B={[4]={26,1.2},[3]={.75,1.8},[2]={8,2}}
local function itemScore(item,slot)
 if not item or not item.link then return nil end
 local ilvl=item.ilvl
 local quality=item.quality
 local loc=item.equipLoc
 -- Old snapshots can be hydrated from the local client item cache.
 if (not ilvl or not quality or not loc) and GetItemInfo then
  local _,_,q,level,_,_,_,_,equip=GetItemInfo(item.link)
  ilvl=ilvl or level;quality=quality or q;loc=loc or equip
 end
 if not ilvl or ilvl<=0 or not quality then return nil end
 loc=loc or fallback[slot]
 local modifier=mods[loc]
 if not modifier then return nil end
 local qualityScale=1
 if quality==5 then qualityScale=1.3;quality=4
 elseif quality==1 or quality==0 then qualityScale=.005;quality=2
 elseif quality==7 then quality=3;ilvl=187.05 end
 local formula=(ilvl>120 and A or B)[quality]
 if not formula then return nil end
 return math.max(0,math.floor(((ilvl-formula[1])/formula[2])*modifier*scale*qualityScale))
end
function HCS_GearScoreCalculate(items,class) -- class retained for compatibility
 local total,scored,missing=0,0,0
 local main=items[16]
 local off=items[17]
 local function loc(item)
  if not item then return nil end
  if item.equipLoc then return item.equipLoc end
  if GetItemInfo and item.link then local _,_,_,_,_,_,_,_,e=GetItemInfo(item.link);return e end
 end
 -- HeroesWoW: every class may dual-wield and equip two-handed weapons in both hands.
 -- Use the equipped weapon configuration, never class-based assumptions.
 -- A paired 2H setup receives half of each 2H weapon's normal 2H contribution
 -- so that the combined weapon budget matches two-handed weighting.
 local dual2h=main and off and loc(main)=='INVTYPE_2HWEAPON' and loc(off)=='INVTYPE_2HWEAPON'
 local titan=dual2h and .5 or 1
 for slot=1,18 do
  if slot~=4 then
   local item=items[slot]
   if item and item.link then
    local value=itemScore(item,slot)
    if value then
     if slot==16 or slot==17 then value=value*titan end
     total=total+value;scored=scored+1
    else missing=missing+1 end
   end
  end
 end
 return math.floor(total),scored,missing
end

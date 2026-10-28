# Importing a character from `UE_game.log` — investigation and design

Status: investigation only (2026-10-28). No product code. Spike scripts live in the
gitignored `docs/local/log-import/` (parser, ID-bridge, grid-match); the log itself is never committed.

**Clean-room statement.** An existing third-party log importer is source-available, not open source. Nothing here was
copied or derived from its code or its ID dictionary. Everything marked **VERIFIED** was
observed directly in one 2.9 MB capture (`UE_game.log`, 30,268 lines, one login) or by matching it against
our own hydrated tli-data (`npm run fetch:data`, SS14 + `crosswalk/SS13`). Everything marked **HYPOTHESIS**
was not proven by this single log. The three third-party write-ups were used only as leads, and every
claim from them that we rely on was re-checked below.

## 0. Coverage checklist

Everything a character can have in TLI Builder, taken from the `Build` interface (`api/client.ts`),
`KNOWN_BUILD_KEYS` (`buildCompat.ts`) and the planner screens, plus the extra concepts the third-party
write-ups mention. Evidence column: **VERIFIED** = observed in our own captures with the field path;
**HYPOTHESIS** = consistent with the captures but not proven; **NOT IN LOG** = no field carries it.
"Bridge" = whether tli-data already carries the game id needed to name it (see section 2).
Captures used: the owner's live log (also supplied as a redacted fixture), its two backups and one
older dump; "live" below means the redacted fixture.

| # | Item (Builder field) | Log source | Evidence | Bridge | Status |
|---|---|---|---|---|---|
| 1 | Hero (`traitId` hero) | `heroCharacterv3OverView.heroPurchaseId` (`18001`), `player.HeroId`, `FightMgr@RoleType` | VERIFIED | no (GAP-5) | id readable, no name table |
| 2 | Hero trait selection (`traitId`, `advancedTraitSelections`, `traitTreeAllocations`) | `…pointOverView.activeId[]` = `1800011/21/31` | VERIFIED ids; meaning HYPOTHESIS | no (GAP-5) | ids only |
| 3 | Trait slot levels (`traitSlotLevels`) | none found | NOT IN LOG | n/a | user input |
| 4 | Hero memories (`heroMemories`, `baseMemory`) | `…reminiscenceOverView.reminiscence[1..3]`, `defaultReminis` | VERIFIED | 12/15 affixes | mostly importable |
| 5 | Memory inventory (`memoryInventory`) | bag pages (30-cap) | VERIFIED but truncated | partial | not complete |
| 6 | Gear: legendary (`gear[]`) | `bag.wearItems` page -1, `UniqueItmId`, `BaseAffix`/`Prefix`/`Suffix` | VERIFIED | 7/7 items, 30/30 affixes | importable |
| 7 | Gear: rare / crafted (base type, affix tiers) | same, `Prefix`/`Suffix`/`…Slots`, `Status` | VERIFIED | **no** (GAP-1, GAP-2) | blocked on ids |
| 8 | Corroded / desecration (`corrosion_type`, `corroded_explicit_indices`) | `Corrode`, affix `source` | VERIFIED field; meaning HYPOTHESIS | base affix 2/2 | partial |
| 9 | Implicits (`implicit_count`, `base_stats`) | `FixedBaseAffix`, `BaseAttrAffix` | VERIFIED | 11/11 | importable (base ambiguity) |
| 10 | Enchant affixes | `Item.EnchantAffixs`, `EnchantSlots` (1 item in live) | VERIFIED field, ids unresolved | no | blocked on ids |
| 11 | Chip / extension affixes | `extAffix` seen on a tree node (prism anchor); none on gear in any capture | NOT SEEN on gear | no | needs a capture with one |
| 12 | Belt blend, tower sequence, vorax flags (`beltBlend`, `towerSequence`, `is_vorax`) | not located; `Status`/`DreamAffixExclusive` may relate | HYPOTHESIS | no | unknown |
| 13 | Active skills + slot (`skills[]`) | `bag.wearItems` page -6 slots 1–5, `skillLayout`, `dressSkillItems` | VERIFIED | 25/25 | importable |
| 14 | Supports / activation medium / noble / magnificent, `support_index` | page -6 slot ids (F11), item `BaseId` | VERIFIED | yes via gameId | importable |
| 15 | Skill & support levels (`level`) | item `SkillItemLevel`/`Level` | VERIFIED | n/a | importable; 3/39 equipped skill objects were cut by the 30-cap (F9) |
| 16 | Support rolls/tiers/ranks (`specific_rolls`, `rank`) | `Prefix[].{Id,DynArgs}` on skill items | VERIFIED field | no (GAP-3) | tier-midpoint fallback |
| 17 | Passive skills (slots 6–9) | page -6 slots 1001/1007/1013/1019 | HYPOTHESIS | yes | needs 2nd build |
| 18 | Talent trees (`slots[].nodeStates`) | `geniusInfos.info[].geniusList[]` | VERIFIED | by geometry (F12) | importable, truncation-limited |
| 19 | Core talents (`coreTalentSelections`) | `bonusGeniusInfo[]` | HYPOTHESIS | partial | needs confirm |
| 20 | **Prisms** (`prisms[]`, `prismInventory`) | `geniusInfos.info[].prismInfo/prismEffectPositions/prismGeniusId` | VERIFIED placement, see F20 | no (GAP-7) | placement importable now, kind/rolls not |
| 21 | Ethereal prism config (`EtherealConfig`) | prism item `Prefix`/`BaseAffix` ids | VERIFIED field, ids unresolved | no | blocked on ids |
| 22 | **Divinity slates** placed (`slates[]`) | `bag.dressingTalentBlocks` + page -4 | VERIFIED items; placement HYPOTHESIS, see F21 | no (GAP-6) | partly reconstructable |
| 23 | Slate inventory (`slateInventory`) | bag pages | VERIFIED but truncated | no | not complete |
| 24 | Pactspirits (`pactSpirits`) | `ContractInfosV2.ContractDatas` (F18) + `ServantInfos` | VERIFIED | **no** (GAP-8) | ids only |
| 25 | Spirit ranks | `ServantInfos.servantData[].starLevel` | VERIFIED, but 30-cap (F18) | n/a | unreliable beyond 30 owned |
| 26 | Rings / destinies / fates (`fates`, `undetermined`) | `ContractInfosV2.pointDatas[]` (`tattoInfo`) | VERIFIED field; ring meaning HYPOTHESIS | no (GAP-9) | partial, 30-cap |
| 27 | Kismets installed | same as 26: kismets are destiny items in `tattoInfo` (BaseId `3503xx`?) | HYPOTHESIS | no | see F22 |
| 28 | **Sage scent-bottle ingredients** (`elixirIngredients`) | `customSkillSlots[].materialSlots[]` | HYPOTHESIS, see F23 | no (GAP-10) | present, unnamed |
| 29 | **Mercenaries + skills** | searched all 34 top-level keys and the post-login lines | NOT IN LOG | n/a | needs another panel (section 8) |
| 30 | Character level (`characterLevel`) | `player.Level`; fallback last `SetPlayerLv` | VERIFIED | n/a | importable |
| 31 | Config: conditions, target/enemy, custom mods, notes, loadouts | none | NOT IN LOG | n/a | user input |
| 32 | Account facts the importer must not touch | `player` ids, `otherInfo`, `guild`, IPs | VERIFIED present | n/a | never read |

## 1. Verified format facts

| # | Fact | Evidence |
|---|---|---|
| F1 | The file starts with a UTF-8 BOM and uses CRLF. Decode as `utf-8-sig`, normalise `\r\n`. | first bytes `EF BB BF` |
| F2 | The login dump is one block: `----Socket RecvMessage STT----GetPlayerData----SynId = N` … `----Socket RecvMessage End----`. This log has exactly one (lines 22156–26751), preceded by a `SendMessage … GetPlayerData` with `+clientLang [en]`. | grep |
| F3 | The block's first line shares its line with the log prefix `[ts][frame]TLNetGame: Display: [Game] `; the tree body follows on the next physical lines (no per-line log prefix). | read |
| F4 | Tree syntax: each line is `|`-padding then one or more `+key` segments, optionally ending in ` [value]`. The **column of each `+`** is the nesting depth. Rule that parses all 4,595 lines: a line whose first `+` is at column *c* pops every open key at column ≥ *c*; its parent is the top of what remains; the rest of the `+key` segments on that line each nest one deeper. Lists are keyed `1,2,3…`. A key with a value has a trailing space in the key text (strip it). | spike parser, whole dump parsed, 33 top-level keys |
| F5 | **Every list is truncated at 30 elements**: the 31st is written as `+31+...` and the rest are dropped. Hit 20× in this dump (tasks, bag pages, skills, talents, pactspirits…). Any count-based logic must treat a 30-element list as "possibly more". | 20 `+...` markers |
| F6 | **The Downloads capture has no `+player` block; two later captures do.** Checked on three more logs from the owner's game folder (live `UE_game.log`, and two `UE_game-backup-*.log` files): each has exactly one `GetPlayerData` dump with 34 top-level keys, the 33 above **plus `player`**, which carries `Name` (no `#digits` discriminator), `Level`, `HeroId`, `HeroPurchaseId`, `SeasonId`, `Exp`, `GeniusCareerId[1..4]`/`GeniusCareerIdStr`, `FollowServant`, plus ids (`PlayerId`, `UserId`, `ChannelId`). Why the Downloads dump lacks it is **not proven**: its Recv header, `SynId`, key set and bracket syntax are otherwise identical, and there is no `+player` anywhere in that file. Most likely the file was edited/redacted after capture (the block holds the name and ids); a different login path is the alternative. Either way an importer must not require `player`: **fallbacks** are the last `AttrUtils:SetPlayerLv = N` after the dump (earlier ones are `= 1` placeholders; Downloads log: 94), `PreLoadHeroId`/`RoleType`, and `geniusInfos.info[].geniusCareerId` (which lists the same careers as `player.GeniusCareerId`). The name is only ever in `player.Name`. | grep |
| F7 | The selected hero is logged outside the dump: `FightMgr@RoleType = 1800` and `Loading@ PreLoadHeroId = 18001`; the dump repeats it as `heroCharacterv3OverView.heroPurchaseId = 18001`. | lines 20904, 20931 |
| F8 | After the dump the client replays item state as `ItemChange@ Reset PageId=P` then `ItemChange@ Add Id=<ItemId> BagNum=1 in PageId=P SlotId=S` (and later `Update` for skills). Pages seen: `-1` gear (9 Adds), `-6` skills (36 Adds then 36 Updates), `-4` divinity slates (7), `-2`, `-10` (empty), `100–103` bags. The `Id` joins to the `+Id [...]` of an item object in the dump. | 269 lines |
| F9 | **All equipped items are fully described in the dump** even though bags are truncated: every `-1` (9/9), `-6` (36/36) and `-4` (7/7) `ItemChange` Id has a full item object in the dump. Bag pages 101/102/103 list 39/58/67 items via `ItemChange` but only 30 each have data (F5). Equipped-state import is therefore complete; "inventory import" is not. **Correction (live fixture):** `dressSkillItems` and `skillLayout` are also capped at 30, and the live account has 39 equipped skill/support items, so 3 of them (slots `302`, `1010`, `1016`) have no item object. Their `BaseId` is still recoverable because the `ItemChange` Id is `<BaseId>_<guid>` (e.g. `7407_…`), but their level and support rolls are not. An importer must treat a skill/support with no object as "name known, level unknown". | cross-check |
| F10 | Gear slot ids (`wearItems[].Index`, `SlotId` on page -1), derived from the resolved base types: 1 helmet, 2 weapon, 4 chest, 5 amulet, 6 ring, 7 ring, 8 belt, 9 gloves, 10 boots (3 = off-hand, empty here). | resolved names |
| F11 | Skill slot ids (page -6): `1–5` = the five active skills, `s01` = that skill's activation medium (`101,201,…,501`), `s02…s0n` = its supports (`102–103`, `202–204`, `302–304`, `402–403`, `502–505`); `1001,1007,1013,1019` = passive skills with supports `1002–1003`, `1008–1009`, `1014–1015`, `1020–1021`. | resolved names; **HYPOTHESIS** for the exact meaning of the passive block until a second build confirms it |
| F12 | Talent grid: log `position{x,y}` ↔ TLI Builder `(column,row)` = **`(y−1, x−1)`** (transposed). 4 of 4 trees match a tree file's occupied-cell set exactly (25/25, 29/29, 30/30, 30/30). `geniusId` is the 8-digit number `PP·10⁶ + y·10⁴ + x·10²` (e.g. `40010300` = prefix 40, y=1, x=3), confirmed on all 120 ids against their `position`. | grid-match spike |
| F13 | Career id → tree, by exact occupied-cell match (a 30-cell truncated list can tie): Downloads log `4` = God of War, `42` = Ronin, `62` = Steel Vanguard; live log (careers `1,12,62,54` per `player.GeniusCareerId`) `1` = God of Might, `12` = Onslaughter, `62` = Steel Vanguard (again), `54` = Lich. So the first digit is the god (1 Might, 4 War, 5 Deception, 6 Machines) and a second digit the hero within that god; a one-digit id is the god tree. Ties on truncated lists (`43`, `54` vs Ranger/Magister) are broken by that rule (`43` ≙ a War hero) and by `player.GeniusCareerId`. Remaining god digits (2, 3) and hero indexes are **HYPOTHESIS**. | grid-match |
| F14 | `talentBlockInfluence` is keyed by the slate's item Id and lists `EffectTalentIds`: the **talent nodes (as geniusIds) each slate slot overrides**. That gives slot→node targets for every installed slate, but not the slate's shape or position on the board. | read |
| F15 | A prism is `geniusInfos.info[n].prismInfo{geniusId, item}` + `prismEffectPositions`; the node under it has `inPrismArea=true`/`disable=true`. See F20 for the full placement rule. | read |
| F16 | Core-talent choice is `bonusGeniusInfo[n].value.geniusId` (e.g. `40001200` = prefix 40, "row 0", x=12). | read |
| F17 | Hero memories: `heroCharacterv3OverView.reminiscenceOverView.reminiscence[1..3]` with `BaseId` 71001/71002/71003, `BaseAttrAffix`, `BaseAffix`, `Suffix` arrays of `{Id, DynArgs[]}`. Hero traits: only `pointOverView.activeId = {1800011,1800021,1800031}`. | read |
| F18 | **Pactspirits (corrected, supersedes the earlier "installed set unknown").** `ContractInfosV2.ContractDatas[]` holds 6 `{areaId, servantId}` entries, listed in arbitrary order; `areaId` 1–3 are the battle slots and 4–6 the reserve (confirmed: both logs that have the block list exactly areaId 1–6). Sort by `areaId` and take the first 3. `ContractInfosV2.unlockInfo[]` has `CPT_SLOT.TotalNum` = **3** on the live account but **1** on the older (level-94) dump, which still lists six `ContractDatas`; so the number of *usable* battle slots is probably `min(3, CPT_SLOT.TotalNum)`, not always 3 (**HYPOTHESIS**, one data point). `player.FollowServant` is the **follower pet**, not a pactspirit (owner, 2026-10-28); it shares the id space (`11230`) but is not in `ContractDatas`. `ServantInfos.servantData[]` = `{servantId, starLevel?}` is the owned collection, **capped at 30**. Level rule from the third-party write-up, `min(6, starLevel+1)` and level 1 when `starLevel` is missing, holds for entries that are visible, but "missing" is ambiguous: on the live account 5 of the 6 contracted spirits are **not in the visible 30**, so their absence reflects the cap and not "level 1". Only `5330` (starLevel 2 → level 3) and `15110` (starLevel 5 → level 6) can be levelled. Rank is therefore *unknown*, not 1, for any spirit missing from the list. | pacts spike, 3 captures |
| F19 | The log contains personal data: platform account name, `playerId`/`userId`/device ids, IP addresses, guild id, chat-free but account-bound progress. | grep |
| F20 | **Prism placement (VERIFIED on the live Onslaughter tree).** `prismInfo.geniusId` (`12060400`) is the **anchor node**: decode with F12 (`y=06,x=04` → Builder column 5, row 3). `prismEffectPositions[]` lists the reflected box as `{x,y}` pairs (6 here: x 3–5, y 6–7), i.e. Builder columns 5–6 × rows 2–4, a 2×3 box that contains the anchor. Nodes in the box carry `inPrismArea=true`; the anchor also has `disable=true` and an `extAffix` (`Id` + `DynArgs`). `prismGeniusId` (`80002000`) and `bonusGeniusInfo[].value.isPrismSkill=true` name the **replacement core talent** the prism grants. The prism item has `BaseId` (`360620`), `RareValue` (3 = rare), `BaseAffix`/`BaseAttrAffix` (implicit lines), and `Prefix[]` (`source` 14) for the crafted slots (area size / middle / advanced). That gives `PlacedPrism.{treeName, anchorCol, anchorRow}` and `EtherealConfig.boxCols/boxRows` directly; the box size convention against Builder's `boxCols/boxRows` and `boxAllocations` still needs one in-app comparison. Which prism it is (kind, rarity-tint, implicit) needs a `BaseId`/affix-id table (GAP-7). Only 4 of the 6 box nodes appear in the truncated `geniusList`, so `boxAllocations` points can be incomplete. | read, one prism |
| F21 | **Divinity slates.** `bag.dressingTalentBlocks[]` (6 on the live account, 7 on the older one) are the *installed* slates; each is `{Item, Index, PageId=-4}`. **`Index` equals the page -4 `SlotId`** and is a board position. All 11 distinct values seen across 4 captures (`22 24 31 33 36 41 43 44 46 53 54`) have both decimal digits in 1–6, which fits **`Index = 10·row + column`, 1-based, on the 6×6 board** and lands every slate on a valid cell of Builder's 24-cell board (HYPOTHESIS, strong; whether it is the shape's top-left cell or another corner is **not** determined). Per item: `BaseId` (`2603xx`/`2605xx` base slates, `2610xx` legendary, `394004` a third kind with `InfluenceId 10001`/`devilBlockAttrId`), `ShapeId` (`1033 1035 1043` base, `2020 2090` legendary), `Direction` (1 or 2 here, likely rotation index), `RareValue` (3 rare, 4, 100 = legendary), `UniqueItmId` (`1003`, `1010` on legendary slates only: the unique-kind key), `EnhanceId`/`EnhancedTimes`/`revertTimes`/`growCount` (upgrades), `BaseTalentList[]` (the fixed effect talents) and `EnchantTalentList[]` + `talentSlotList[{color, talentId, rarity}]` (the rolled slots; `color` Orange/Purple). Shape cell counts and the meaning of `ShapeId`/`Direction` digits cannot be checked from the log alone because no ground-truth board is attached to a capture (see section 8). | 4 captures |
| F22 | **Slate effects are talent ids in geniusId format.** `talentBlockInfluence[]` is keyed by the slate item Id and lists `EffectTalentIds` (`BaseTalentList` + enchant talents, in order), `TalentIdDevour`, `TalentIdInfluence` (e.g. `-30`) and, for base slates, `DevilLineBoostTalentIds/Influence` (`40`). These ids decode with the F12 rule (`PP·10⁶ + y·10⁴ + x·10²`) to a **talent in a career tree**, so a slate slot is "copy of node (tree, col, row)", exactly Builder's `SavedSlateSlot.selectedNodeId` model. Ids with `y=00` are core talents (`63001300`, `21001100`, x = core slot as in F16), and `9000006x` is a different class of id (the base talent of the `394004` kind). The prefix `PP` is the **career id** (F13), so `41–44` are presumably four heroes of one god (F13 rule: first digit = god; HYPOTHESIS). A complete `PP` → tree table is needed; we can resolve `1, 12, 62, 54, 4, 42` from the owner's trees and need captures of other careers (or the owner's slates' trees) for `11 13 14 21 34 41 43 44 63`. Equivalent `slate-mods.json` rows are keyed by node name, so the join is `decoded node → name → row`. | read + decode, 23 ids |
| F23 | **Installed destinies/fates live in `ContractInfosV2.pointDatas`** (the "rings"). `contractPointId` = `<areaId><2-digit node>` (`104` = servant area 1, node 04; `211` = area 2 node 11); `selectContract` 1 = empty, **2 = installed**, and then `tattoInfo` carries the item (`BaseId` `350301`/`350001`/`350003`, `Level`, `BaseAffix` `{Id, DynArgs}`, `DropSource`). In the live capture all three installed destinies are in area 1 (the first battle servant). `unlockInfo` gives node counts (`CPT_SMALL` 9, `CPT_MIDDLE` 4, `CPT_SLOT` 3, `CPT_SECRET` 15). **Truncation:** `pointDatas` is capped at 30 entries (a 31st `...`) but each of 6 areas has ≥11 nodes, so **most nodes are cut**; installed destinies beyond the visible 30 are lost, and the visible 30 is not area-ordered. Whether nodes ≥ N are "mid"/"outer" rings, and whether `3500xx` vs `3503xx` separates micro fates from medium fates/kismets, are HYPOTHESES. No log line names a destiny, kismet or ring. | 2 captures |
| F24 | **Sage scent bottle is probably `customSkillSlots`.** `customSkillSlots[]` is `{id, customId, state?, materialSlots[]}`; each material slot is `{index, optionIds[3], chooseOptionId, effectOptionIds[]}`. The live account has two entries (3 slots and 2 slots), the hero is `1800` (that this is the Sage is not proven by the log), and the trait data for the Sage's `Licorice Note` says a Basic Scent Bottle holds 2 ingredients, with one extra from an advanced trait; each ingredient *category* offers exactly 3 ingredients (`_hero_traits.json … ingredients[].categories[].items`). That matches `optionIds` (3 per slot) and `chooseOptionId` (the picked one): option ids have the form `<customId><slot><choice><tier>` (e.g. `1132` = bottle 1, slot 1, choice 3). `skillPosRequirements.customSlotRequirementMap` ties a custom slot to a skill type (`tags`, `types`). Mapping a choice to an ingredient name needs the category of each slot (not stated) and a confirming ground truth (section 8). HYPOTHESIS, but this is the first time the data is shown to be present in the dump. | read |
| F25 | **Searched and NOT present:** mercenaries or their skills (no key or text in any of the 34 top-level keys, nor `merc|hire|assist|partner` in the live or backup logs), `backupSkillDto` and `skillAdditionalAffix` (both empty), a destiny/kismet/ingredient name anywhere, and any pactspirit name or `servantId → name` table. The `tasks`, `functions`, `rewards`, `fashions`, `guideInfo`, `helpInfo`, `achievementInfos`, `growUpDto`, `SP3Base`, `userGem`, `otherInfo` and `SkillSlot` keys hold progression, shop or season-activity data only (`SP3Base` is a map-event state, not a build). | key-by-key read |

Note (owner, 2026-10-28): a third-party desktop companion app (v2.0.1) only parses `GetPlayerData` gear sections
(pages -1 and 100) for its profit/stats features; it has no `player` parsing and no log-to-build import,
and it does not make the game write the dump. The web planner remains the only log-to-build importer known.

## 2. ID bridge (this log vs our data)

Rates are unique-ids-hit / unique-ids-in-log, searched across every numeric value and numeric key in
SS12–SS14 + crosswalk (`docs/local/log-import/bridge*.py`).

| Log ID kind | Hit | Where it lands in our data | Verdict |
|---|---|---|---|
| Legendary `UniqueItmId` | **7/7** | `_legendary_gear.json items[].internal_id` (also `crosswalk/SS13/legendaries.json` gameId) | resolved |
| Legendary affix ids (`51…`) | **30/30** | `_legendary_gear.json … variants.base.explicits[].modifier_id`; corroded: `variants.corroded.explicits[]` | resolved |
| Gear implicits (`FixedBaseAffix`/`BaseAttrAffix`, e.g. `660002`) | 11/11 | `_craft_base_items.json base_items[].implicits[].modifier_id` — and these, not `BaseId`, identify the **base item**, with some ambiguity: `580010` is shared by several chests | resolved with disambiguation |
| Corrosion base affix (`600…`) | 2/2 | `_craft_base_types.json corrosion_base_affixes[].modifier_id` | resolved |
| **Gear `BaseId`** (`1219,3011,4639…`) | **0/9** | no numeric base id anywhere in tli-data | **GAP-1** |
| **Crafted/rare gear affix ids** (`106100001`, `110100001`, `140100401`, `104900002`, …) | **0/12** | `_craft_base_types.json affixes[]` carries `modifier_id` + `tier` but in a 7-digit space (`1502300`); the log uses 9-digit ids | **GAP-2** |
| Affix `source` (`6`,`12`) and `Corrode` flag | n/a | `source` is a game flag (6 = corrosion/desecration base, 12 = a special source) — meaning not documented | **GAP-2b** |
| Skill `BaseId` (all 36 equipped, 25 unique) | **25/25** | `crosswalk/SS13/skills.json rows[].compendium.gameId` (721/721 rows carry one); all 25 names exist in SS14 `_skills.json` | resolved (via the SS13 crosswalk) |
| Skill support categories | resolved | support / activation medium / noble all resolve by the same `gameId` (e.g. 8003–8006 mediums, 7746 noble) | resolved |
| Skill support **line choices/tiers** (`Prefix{Id,DynArgs}` `771031022…`) | **0/5** | none | **GAP-3** |
| `customSkillSlots` option ids (`1131…`) | 0/3 | none | GAP-3b |
| Hero memory `BaseId` 71001–71003 | **3/3** | `_hero_memories.json memory_types[].internal_id` | resolved |
| Memory affix ids (`4021…`, `4022…`) | **12/15** | `crosswalk/SS13/memory-affixes.json rows[].compendium.gameId` | mostly resolved; the 3 `4031…` BaseAttrAffix ids miss (**GAP-4**) |
| Hero id (18001/1800) and trait ids (`1800011…`) | **0/4** | `crosswalk/SS13/hero-traits.json` `gameId` is null on all 27 rows | **GAP-5** |
| `geniusId` | 0/119 by value, **resolved by geometry** | decode `PPYYXX00` → tree + `(x,y)` → `(column,row)` (F12); no ids needed for the 3 trees that matched exactly | resolved by rule; verify prefixes (F13) |
| Core talents (`bonusGeniusInfo`) | decodes to `x=12` etc. | `crosswalk/SS13/core-talents.json` has `slotIndex`; needs one confirming log | **HYPOTHESIS**, partial |
| Slate `BaseId` (`260301…`) | **0/5** | none | **GAP-6** |
| Slate effect/`BaseTalentList` ids (`90000066`, …) | **0/19** | `crosswalk/SS13/slate-mods.json` carries only uuids | GAP-6 |
| `EffectTalentIds` (slate→node) | decodes by rule | node geniusId → tree/(col,row) (F12/F14) | resolved by rule |
| Prism `BaseId` 360614 and affixes `1204…` | **0/3** | `crosswalk/SS13/prisms.json` has no ids | **GAP-7** |
| Pactspirit `servantId` | **0/30 real** (4 numeric collisions with unrelated skill ids) | `crosswalk/SS13/pactspirits.json` `gameId` null on 175/175 | **GAP-8** (see section 5 for the clean-source search) |

**Bottom line:** equipped legendary gear, all skills and supports (by name), hero memories (mostly), and the
talent grid import with data we already have. Rare/crafted gear, support line rolls, hero traits, slates,
prisms and pactspirits need game-id fields that tli-data does not carry yet.

## 3. Mapping to the TLI Builder build model

Targets are the `Build` interface in `src/renderer/src/api/client.ts` and `KNOWN_BUILD_KEYS`
(`buildCompat.ts`). The frozen `tli1_` codec is untouched: an importer builds a `Build` object
client-side and hands it to the existing open/save path; it never edits `backend/build_code.py`.

| Log section | Fills | Quality |
|---|---|---|
| `bag.wearItems` page `-1` | `gear[]` (`EquippedGearItem`: legendary → `item_id` from `internal_id`; affix `DynArgs` → rolls; `Corrode` → `corrosion_type`) | legendary: full. rare/crafted: needs GAP-1/2; until then import as an "unresolved item" placeholder (slot, item level, raw ids kept) with no stats |
| `bag.wearItems` page `-6` + slot ids | `skills[]` (`slot` 1–5 active, 6–9 passive; `supports[]` by `support_index`; `level`, noble `rank`) | names+levels full; support line rolls lost (GAP-3), so engine uses its tier-midpoint default |
| `geniusInfos` | `slots[]` (`TreeSlot.nodeStates` from `point`; `coreTalentSelections` from `bonusGeniusInfo`) | node points full for lists ≤30 cells; truncation (F5) drops the last cells of dense trees — **partial** |
| `geniusInfos…prismInfo` + `prismEffectPositions` + `prismGeniusId` | `prisms[]` (`PlacedPrism.treeName/anchorCol/anchorRow`, `EtherealConfig.boxCols/boxRows`, replacement core talent) | anchor and box: full (F20); kind/rolls need GAP-7; import prisms in the same pass as the tree so `inPrismArea` nodes are not double-counted as plain allocations |
| `bag.dressingTalentBlocks` + `talentBlockInfluence` | `slates[]` (`kind`, `shapeIndex`, `orientationIndex`, `anchor`, `slots[].selectedNodeId`) | slot effects: full via decoded talent ids (F22); anchor: `Index` → (row, col) probable (F21); shape/rotation from `ShapeId`/`Direction` unproven → ask owner (section 8) |
| `heroCharacterv3OverView.reminiscenceOverView` | `heroMemories[]` | base type + 12/15 affixes today |
| `heroPurchaseId`/`activeId` | `traitId`, `traitSlotLevels` | needs GAP-5 |
| `ContractInfosV2.ContractDatas` + `ServantInfos` | `pactSpirits[]` (`itemId`, `rank`) | installed = the first usable areaId slots (F18); rank only when `starLevel` is visible; names need GAP-8 |
| `ContractInfosV2.pointDatas` | `fates` (`<spiritSlotIdx>:<nodeDataIdx>`), kismets | installed items readable (`tattoInfo`), but capped at 30 of ≥66 nodes and unnamed (F23) |
| `customSkillSlots` | `elixirIngredients` (slot → `{category: name}`) | choices present, unnamed (F24) |
| `SetPlayerLv` (post-dump) | `characterLevel` | yes |
| _not in log_ | `conditionState`, `targetConfig`, `enemyConfig`, `customMods`, `notes`, loadouts, divinity-slate geometry, support line choices (until GAP-3), pact destinies | user-supplied after import |

## 4. Privacy and UX

* **Client-side only.** Read the file in the renderer (`File.text()` / a main-process read for the
  Electron app); never upload. Parse in memory, keep only the derived `Build`, discard the text. Do not
  log or persist playerId/userId/account name/IPs (F19) — the importer should never read them.
* **Finding the file.** Default Steam path hint (`…\Torchlight Infinite\UE_game\TorchLight\Saved\Logs\UE_game.log`),
  a file picker (web build can only use a picker), and in Electron an optional "scan known Steam
  libraries" button. Accept multiple files and sort by modification time, since the game rolls
  `UE_game-backup-*.log` on each start; process newest dump first.
* **Missing dump.** The block is only written at login (this log has one; whether the game rotates or overwrites the file on launch was not tested — HYPOTHESIS): if no
  `GetPlayerData` block is found, say exactly that and tell the player to relaunch the game, log the
  character in, and re-pick the file (the file must not be deleted by the game before the player picks it).
* **Name is optional (F6).** Use `player.Name` when present as an opaque string. Per the owner, the `#digits` suffix
  only appears when a chosen name is a duplicate, so never require or strip a `#NNNN` pattern for identity. Otherwise
  label dumps by timestamp + hero + level. Each of the three owner files (live + 2 backups) holds one
  dump, so multi-file import = one candidate dump per file; list them newest-first and let the player choose.
  The player block's ids are never displayed or stored.
* **Truncation notice (F5).** Show an import report ("found / partial / missing") that names which sections
  were truncated at 30 entries, so users know the talent tree may be incomplete.
* **Trust.** The log is untrusted input: bounded line counts, bounded tree depth, no `eval`, no keys
  used as property names without a null-prototype map.

## 5. Gaps and what fills them

| Gap | Fill |
|---|---|
| GAP-1 gear base id | crawler field: capture the item `BaseId` per base item (`_craft_base_items.json`); interim: resolve via implicit modifier ids (ambiguous for shared implicits) |
| GAP-2 crafted affix ids/tiers | crawler: emit the 9-digit affix `modifier_id` and tier in `_craft_base_types.json affixes[]`; document `source` flags |
| GAP-3 support line rolls | crawler: ids for support/medium `Prefix` lines; or accept engine midpoints |
| GAP-4 memory base-attr ids | extend `memory-affixes.json` with the `4031…` base-stat ids |
| GAP-5 hero + trait ids | add hero id and trait `gameId`s (crosswalk `hero-traits.json` is all null) |
| GAP-6 slate ids | add slate `BaseId` and `BaseTalentList` ids to `slate-mods.json` |
| GAP-7 prism ids | add prism `BaseId` and affix ids |
| GAP-8 pactspirit ids | map `servantId` ↔ spirit. **Clean-source search (2026-10-28):** (a) tli-data and the crosswalk carry no servant id (`gameId` null on 175/175 and none in `_pact_spirits.json`); (b) the game's loose files hold only ids: the per-account `Local/AccountCache/*/NewPetRedDotData` JSON lists ~148 servant ids with no names, and the packs that hold the config tables are AES-encrypted with no known key (`tli-decompiler/TLI_DATA_RECON.md`), so there is no sanctioned game-file route; (c) no log line pairs an id with a name. What the ids do show is structure: `servantId = 1000·family + 100·tier + 10·variant` (tier 1–5, variant 1–3), where the tli-data names (`Awooawoo - Violet`, …) look like creature + colour. That is a HYPOTHESIS to test, not a table. **Clean way to fill it:** observation. The owner names the spirits in the six `ContractDatas` slots and the follower pet in game (7 ids, ready to ask) and every future capture/relog adds more; players submitting `id → name` pairs from their own panel is the same method. Do not copy any third-party bundle table. |
| GAP-9 destiny / kismet / ring ids | `tattoInfo.BaseId` (`350001`, `350003`, `350301`, …) ↔ `_destiny.json` entries (193, no ids); same method: owner reads the three installed destinies' names |
| GAP-10 scent-bottle option ids | `customSkillSlots` option ids (`1112…`, `2231…`) ↔ ingredient names; owner reads the five slots (section 8) |
| F13/F16 | one extra log from a different class/god to confirm career-prefix and core-talent rules; the same logs complete the slate-talent `PP` → tree table (F22) |
| Truncation (F5) | the 30-entry cap also hits `pointDatas`, `servantData`, `dressSkillItems`, `skillLayout`, `geniusList`; if any other panel or message returns the same data uncapped it would remove most "partial" rows. Nothing found yet (F25) |

## 6. Implementation plan (follow-up tasks)

1. **Parser library** (M, ~2–3 days): pure TS module `src/renderer/src/importers/ueLog/` — decode, find
   dumps, bracket-tree parse (F4), `ItemChange` replay (F8), truncation flags (F5), level/hero extraction (F6/F7).
   Fixture-tested on a redacted copy of the log (strip player/account/IP lines). No UI.
2. **Skills + supports + level import** (S, ~1–2 days): `skills[]`, `characterLevel`, hero id, via the SS13 crosswalk
   `gameId` (data already present). Needs a data-loader that exposes `gameId`→skill.
3. **Talent grid import** (S–M, ~2 days): geometry rule (F12), prefix table (F13), core-talent selection;
   truncation warning.
4. **Legendary gear import** (S, ~1–2 days): `internal_id` + affix `modifier_id` + rolls + corrosion.
5. **tli-data/crawler fields** (L, owner decision — out of this repo): GAP-1…GAP-10. Unblocks rare gear,
   traits, slates, prisms, pactspirits.
6. **UI** (M, ~2–3 days): ImportPanel entry "From game log", report (found/partial/missing), privacy copy,
   multi-file handling.
7. **Prisms (placement now, kind after step 5), slates (slot effects now, placement after the section 8 board check), hero memories, pactspirit/destiny/scent-bottle naming** (M each).

Rough total for a useful "skills + talents + legendary gear + level" import: ~1.5–2 weeks; full
fidelity depends on step 5.

## 7. Open questions for the owner

1. Should step 5 (crawler id fields, now GAP-1…GAP-10) be scheduled, since it gates most of the long tail?
2. Is a main-process "scan for the log" button acceptable for the Electron build (read-only, local)?
3. May the redacted fixture (`UE_game-redacted.log`) be committed as a test fixture? It is kept out of git for now (it lives in the gitignored `docs/local/`).

## 8. What we need from the owner (ground truth, nothing to relog unless noted)

All answers below come from looking at the owner's own character; they turn HYPOTHESIS rows into VERIFIED.

1. **Pactspirits (GAP-8).** The names of the spirits in battle slots 1, 2, 3 and reserve slots 4, 5, 6 (live ids `5330`, `18230`, `19230`, `15130`, `15120`, `15110`), and the follower pet (`11230`). Their star/rank in the panel too (expected: slot 1 rank 3, `15110` rank 6; others unknown because of the 30-entry cap, F18).
2. **Destinies / rings (GAP-9, F23).** Open the pact panel on the spirit in slot 1: the names and which node (inner/mid/outer ring, position) hold the three installed items (ids `350301`, `350001`, `350003`). Also whether any other spirit has one installed (we only see 30 of the nodes).
3. **Divinity slates (F21).** A screenshot of the divinity board with all six slates placed, plus the slate names. That lets us fit `Index`, `ShapeId` and `Direction` to cells.
4. **Sage's scent bottles (F24, GAP-10).** For each of the two bottles, the ingredient in each slot (and the ingredient category of the slot): the five picked option ids are `2231`, `2121` (bottle with 2 slots) and `1232`, `1132`, `1312` (bottle with 3 slots). Please also confirm the character is the Sage.
5. **Mercenaries and their skills (F25).** Nothing in the login dump. After the next login, **open the mercenary panel and the mercenary skill panel once**, then give us the new `UE_game.log` (it is rewritten each launch, so copy it first). If a later message carries them they will be in that file after the dump.
6. **Kismets.** Open the kismet / destiny panel on the spirit in slot 1 (and one other spirit with a kismet, if any) before copying the log, for the same reason.
7. **Gear we have not seen:** a capture where an item carries a **chip / extension**, a **tower sequence** or a **belt blend**, so those rows can be filled. A relog after equipping one is enough.

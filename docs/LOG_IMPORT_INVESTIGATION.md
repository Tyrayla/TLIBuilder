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
| 12 | Belt blend (`beltBlend`) | `EnchantAffixs[1].Id` on the belt (`3401001`, `source` 13) = the blending-ritual `modifier_id` ("Restores 3 % of Life on defeat", owner-confirmed) | VERIFIED (F26) | yes (`blending_rituals.json`) | importable |
| 12b | Tower sequence, vorax flags (`towerSequence`, `is_vorax`) | not located | NOT SEEN | no | needs a capture with one |
| 13 | Active skills + slot (`skills[]`) | `bag.wearItems` page -6 slots 1–5, `skillLayout`, `dressSkillItems` | VERIFIED | 25/25 | importable |
| 14 | Supports / activation medium / noble / magnificent, `support_index` | page -6 slot ids (F11), item `BaseId` | VERIFIED | yes via gameId | importable |
| 15 | Skill & support levels (`level`) | item `SkillItemLevel`/`Level` | VERIFIED | n/a | importable; 3/39 equipped skill objects were cut by the 30-cap (F9) |
| 16 | Support rolls/tiers/ranks (`specific_rolls`, `rank`) | `Prefix[].{Id,DynArgs}` on skill items | VERIFIED field | no (GAP-3) | tier-midpoint fallback |
| 17 | Passive skills (slots 6–9) | page -6 slots 1001/1007/1013/1019 | HYPOTHESIS | yes | needs 2nd build |
| 18 | Talent trees (`slots[].nodeStates`) | `geniusInfos.info[].geniusList[]`; node id = tlidb `talent_id` (119/120 match) | VERIFIED | **yes, by id** (F27) | importable; 13 of 31 trees can lose 1-2 top-row nodes to the 30-cap (section 9) |
| 19 | Core talents (`coreTalentSelections`) | `bonusGeniusInfo[]` `geniusId` (`y=00` ids, e.g. `54001300`) = tlidb core-talent `talent_id` | VERIFIED id join (F27); slot rule HYPOTHESIS | yes | importable |
| 20 | **Prisms** (`prisms[]`, `prismInventory`) | `geniusInfos.info[].prismInfo/prismEffectPositions/prismGeniusId` | VERIFIED placement (F20) | no (GAP-7) | placement importable now, kind/rolls not |
| 21 | Ethereal prism config (`EtherealConfig`) | prism item `Prefix`/`BaseAffix` ids | VERIFIED field, ids unresolved | no | blocked on ids |
| 22 | **Divinity slates** placed (`slates[]`) | `bag.dressingTalentBlocks` + page -4; effect slots are tlidb `talent_id`s | VERIFIED against the owner's board screenshot (F21): 6 items = 8 pieces, every `Index` falls inside its piece | partial: effects yes (F27), kinds need ids (GAP-6) | placement + effects importable; kind by `BaseId`/`UniqueItmId` |
| 23 | Slate inventory (`slateInventory`) | bag pages | VERIFIED but truncated | no | not complete |
| 24 | Pactspirits (`pactSpirits`) | `ContractInfosV2.ContractDatas` (F18) + `ServantInfos` | VERIFIED; 6 id/name pairs from the owner (F28) | **no** (GAP-8) | 6 of 181 named |
| 25 | Spirit ranks | `ServantInfos.servantData[].starLevel` | VERIFIED, but 30-cap (F18) | n/a | unreliable beyond 30 owned |
| 26 | Rings / destinies / fates (`fates`, `undetermined`) | `ContractInfosV2.pointDatas[]` (`tattoInfo.BaseId`): micro fates `3500NN`, medium fates `3503NN` (NN = the tlidb icon number) | VERIFIED for 3 ids, rest HYPOTHESIS (F29) | no (GAP-9) | partial, 30-cap but unions across logins |
| 27 | Kismets installed | same field; the kismet id range has not been seen (the visible nodes held none) | NOT YET SEEN | no | needs more logins (section 9) |
| 28 | **Sage scent-bottle ingredients** (`elixirIngredients`) | `customSkillSlots[].materialSlots[].chooseOptionId`; third digit = position of the item in its tlidb category | VERIFIED on 5 of 5 owner-named picks (F24) | yes (`_hero_traits.json`) | importable |
| 29 | **Mercenaries / followers + skills** | not in the dump; the client has a mercenary UI (`SNMercenaryMain`, `SNMercenarySkillBag`) but opening it logs no data message (F30) | NOT IN LOG | n/a | not importable from the log |
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
| F9 | **All equipped items are fully described in the dump** even though bags are truncated: every `-1` (9/9), `-6` (36/36) and `-4` (7/7) `ItemChange` Id has a full item object in the dump. Bag pages 101/102/103 list 39/58/67 items via `ItemChange` but only 30 each have data (F5). Equipped-state import is therefore complete; "inventory import" is not. **Correction (live fixture):** the equipped skill bar is larger than the 30-entry cap: `dressSkillItems`, `skillLayout` and `skills.skills` are each capped at 30, the live account has 39 equipped skill/support items, and the three lists are re-shuffled at every login. One dump therefore carries a full item object for 36 of 39 (searching all three lists), two logins carry all 39 (section 9). `BaseId` is always recoverable from the post-login `ItemChange` Id (`<BaseId>_<guid>`). | cross-check |
| F10 | Gear slot ids (`wearItems[].Index`, `SlotId` on page -1), derived from the resolved base types: 1 helmet, 2 weapon, 4 chest, 5 amulet, 6 ring, 7 ring, 8 belt, 9 gloves, 10 boots (3 = off-hand, empty here). | resolved names |
| F11 | Skill slot ids (page -6): `1–5` = the five active skills, `s01` = that skill's activation medium (`101,201,…,501`), `s02…s0n` = its supports (`102–103`, `202–204`, `302–304`, `402–403`, `502–505`); `1001,1007,1013,1019` = passive skills with supports `1002–1003`, `1008–1009`, `1014–1015`, `1020–1021`. | resolved names; **HYPOTHESIS** for the exact meaning of the passive block until a second build confirms it |
| F12 | Talent grid: log `position{x,y}` ↔ TLI Builder `(column,row)` = **`(y−1, x−1)`** (transposed). 4 of 4 trees match a tree file's occupied-cell set exactly (25/25, 29/29, 30/30, 30/30). `geniusId` is the 8-digit number `PP·10⁶ + y·10⁴ + x·10²` (e.g. `40010300` = prefix 40, y=1, x=3), confirmed on all 120 ids against their `position`. | grid-match spike |
| F13 | Career id → tree, by exact occupied-cell match (a 30-cell truncated list can tie): Downloads log `4` = God of War, `42` = Ronin, `62` = Steel Vanguard; live log (careers `1,12,62,54` per `player.GeniusCareerId`) `1` = God of Might, `12` = Onslaughter, `62` = Steel Vanguard (again), `54` = Lich. So the first digit is the god (1 Might, 4 War, 5 Deception, 6 Machines) and a second digit the hero within that god; a one-digit id is the god tree. Ties on truncated lists (`43`, `54` vs Ranger/Magister) are broken by that rule (`43` ≙ a War hero) and by `player.GeniusCareerId`. Remaining god digits (2, 3) and hero indexes are **HYPOTHESIS**. | grid-match |
| F14 | `talentBlockInfluence` is keyed by the slate's item Id and lists `EffectTalentIds`: the **talent nodes (as geniusIds) each slate slot overrides**. That gives slot→node targets for every installed slate, but not the slate's shape or position on the board. | read |
| F15 | A prism is `geniusInfos.info[n].prismInfo{geniusId, item}` + `prismEffectPositions`; the node under it has `inPrismArea=true`/`disable=true`. See F20 for the full placement rule. | read |
| F16 | Core-talent choice is `bonusGeniusInfo[n].value.geniusId` (e.g. `40001200` = prefix 40, "row 0", x=12). | read |
| F17 | Hero memories: `heroCharacterv3OverView.reminiscenceOverView.reminiscence[1..3]` with `BaseId` 71001/71002/71003, `BaseAttrAffix`, `BaseAffix`, `Suffix` arrays of `{Id, DynArgs[]}`. Hero traits: only `pointOverView.activeId = {1800011,1800021,1800031}`. | read |
| F18 | **Pactspirits (owner ground truth, 2026-10-28).** `ContractInfosV2.ContractDatas[]` holds 6 `{areaId, servantId}` entries in arbitrary order; `areaId` 1-3 are the battle slots, 4-6 the reserve. Sort by `areaId`, take the first 3. Owner names for the live character: slot 1 `5330` = **Preserver of Eternity**, slot 2 `18230` = **Kitty Express**, slot 3 `19230` = **Elixir Fairies**. The reserve changed between the two logins in `UE_game.log`: login 1 (the redacted fixture) had `15110/15120/15130`, login 2 has `6330/6130/19330`, and the owner's reserve (Chalk Spirit, Captain Shadow, Twilight Sparks) matches login 2, so **the owner did not misremember and the earlier reading was of an older reserve**. The two names that share family `6` (`6130`, `6330`) are different spirits, and `19230`/`19330` (family 19) are Elixir Fairies and Twilight Sparks, so **the family/tier/variant formula is not a naming rule**: the digits group related spirits but do not identify a name. Treat servant ids as opaque keys and fill them by observation (section 10). `CPT_SLOT.TotalNum` = 3 on the live account and 1 on the older level-94 dump (which still lists six contracts), so usable battle slots are probably `min(3, CPT_SLOT.TotalNum)` (HYPOTHESIS, one data point). `ServantInfos.servantData[]` = `{servantId, starLevel?}` is the owned collection, **capped at 30 and re-shuffled at every login** (two logins of the same character: 53 distinct ids). Rank = `min(6, starLevel+1)`, level 1 if `starLevel` is absent, holds for entries that are visible, but absent is ambiguous: 4 of the 6 contracted spirits are outside the visible 30 in login 1 and 5 of 6 in login 2 (different ones). Rank is therefore unknown, not 1, unless the spirit is visible in some dump of the same character. `player.FollowServant` (`11230`, unchanged across both logins): see F30 for what it is. | pacts spike, 4 captures |
| F19 | The log contains personal data: platform account name, `playerId`/`userId`/device ids, IP addresses, guild id, chat-free but account-bound progress. | grep |
| F20 | **Prism placement (VERIFIED on the live Onslaughter tree).** `prismInfo.geniusId` (`12060400`) is the **anchor node**: decode with F12 (`y=06,x=04` → Builder column 5, row 3). `prismEffectPositions[]` lists the reflected box as `{x,y}` pairs (6 here: x 3–5, y 6–7), i.e. Builder columns 5–6 × rows 2–4, a 2×3 box that contains the anchor. Nodes in the box carry `inPrismArea=true`; the anchor also has `disable=true` and an `extAffix` (`Id` + `DynArgs`). `prismGeniusId` (`80002000`) and `bonusGeniusInfo[].value.isPrismSkill=true` name the **replacement core talent** the prism grants. The prism item has `BaseId` (`360620`), `RareValue` (3 = rare), `BaseAffix`/`BaseAttrAffix` (implicit lines), and `Prefix[]` (`source` 14) for the crafted slots (area size / middle / advanced). That gives `PlacedPrism.{treeName, anchorCol, anchorRow}` and `EtherealConfig.boxCols/boxRows` directly; the box size convention against Builder's `boxCols/boxRows` and `boxAllocations` still needs one in-app comparison. Which prism it is (kind, rarity-tint, implicit) needs a `BaseId`/affix-id table (GAP-7). Only 4 of the 6 box nodes appear in the truncated `geniusList`, so `boxAllocations` points can be incomplete. | read, one prism |
| F21 | **Divinity slates: placement fitted to the owner's board screenshot (6 items = 8 pieces).** `bag.dressingTalentBlocks[]` are the installed slates (`{Item, Index, PageId=-4}`); `Index` equals the page -4 `SlotId`. **`Index = 10*column + row`, both 1-based, column from the left and row from the top as drawn** (a first guess of `10*row + column` was rejected: it put both legendary slates inside one red piece). Fit on the 6x6 board (the 24 valid cells are all covered, 4+3+4+4+2+7 = 24): `394004` (Nether King's Judgement, `Index` 22, `talentSlotList[1..3].effectDevilBlockIdx`) is **one item that draws the three 1x1 skulls**; only the first skull (c2,r2) is in `Index`, the other two (c5,r2), (c5,r5) are not in the log (HYPOTHESIS: fixed by `devilBlockAttrId` 13). `260504` (shape `1035`, `Direction` 1, `Index` 31) = the God of Might slate on c3r1, c4r1, c3r2, c3r3. `261003` (shape `2020`, Dir 1, `Index` 36) = Fallen Starlight on c3r6, c4r6. `261010` (shape `2090`, Dir 2, `Index` 24) = Pedigree on c1r3, c2r3, c1r4, c2r4, c3r4, c2r5, c3r5 (exactly Builder's `pedigree` orientation 1). `260304` (shape `1033`, no Dir, `Index` 43) = God of War on c4r2, c4r3, c5r3, c6r3 (Builder `L1` orientation 0). `260306` (shape `1043`, Dir 2, `Index` 44) = God of War on c4r4, c5r4, c6r4, c4r5 (`L2` orientation 2). **The coordinator's rough read was correct** (translated: GoM r1c3,r1c4,r2c3,r3c3 etc.). Findings: `Direction` equals the Builder `orientationIndex` for the 3 base slates (absent = 0; 3/3) and is 1-based for the 2 legendary slates (`Direction` 2 = orientation 1; 2/2), so the legendary base is probably `Direction-1` and the base one a different convention (HYPOTHESIS; mirrored/flipped pieces are not covered by this sample). `ShapeId` `1033`/`1035` are both L1 (one rotation apart) and `1043` is L2, so its last digit seems to carry orientation (HYPOTHESIS). `Index` is a cell inside its piece but not a fixed corner (top-left on four, an inner cell on `260304` and Pedigree): which cell is the anchor is unresolved, so the import rule is "find the unique placement of the known piece that contains `Index` and tiles the board". Per item also: `BaseId` (`2603xx` seen on two War slates, `2605xx` on the Might slate, `2610xx` legendary, `394004`), `RareValue` (3 / 4 / 100 = legendary), `UniqueItmId` (`1003`, `1010` on legendary only), `EnhanceId`/`EnhancedTimes`/`revertTimes`/`growCount`, `BaseTalentList[]` + `EnchantTalentList[]` + `talentSlotList[{color, talentId, rarity}]`. | owner screenshot + 6 items |
| F22 | **Slate effects are tlidb talent ids.** `talentBlockInfluence[]` is keyed by the slate item Id and lists `EffectTalentIds` (`BaseTalentList` + enchant talents, in order), `TalentIdDevour`, `TalentIdInfluence` (e.g. `-30`) and, for base slates, `DevilLineBoostTalentIds/Influence` (`40`). Every `EnchantTalentList`/`talentSlotList` id (10/10) and 13 of 14 `BaseTalentList` ids equal a tlidb `talent_id` in our crawler output (F27), so a slate slot resolves by id to a named node in a named tree: `43060400` = Ranger medium talent "+18 % Melee Damage", `42070500` = Ronin legendary medium talent "+20 % Fervor effect", `63001300` = Alchemist core talent. That is exactly Builder's `SavedSlateSlot.selectedNodeId` model, with no geometry guess. The only miss is `90000061`, the base talent of the Nether King slate. `Color` Orange/Purple and `rarity` per slot are also present. | read + id join |
| F23 | **Installed destinies/fates/kismets live in `ContractInfosV2.pointDatas`.** `contractPointId` = `<areaId><2-digit node>` (`104` = area 1 node 04); `selectContract` 1 = empty, **2 = installed** and then `tattoInfo` holds the item (`BaseId`, `Level`, `BaseAffix{Id, DynArgs}`, `DropSource`). `unlockInfo` gives `CPT_SMALL` 9, `CPT_MIDDLE` 4, `CPT_SLOT` 3, `CPT_SECRET` 15. **The list is capped at 30 and shuffled at every login**, so installed destinies are seen with probability about 30/N per login (N is at least 51: the union of three dumps already has 51 distinct node ids over 6 areas). Observed installed items across the two logins of the live character: `104` = `350003`, `105` and `106` = `350001`, `109` = `350301` (four of the owner's six). F29 explains what they are. No log line names a destiny, kismet or ring; ring/set boundaries by node index are a HYPOTHESIS (the owner's "2nd/3rd set of micros" fits nodes 4-6 holding lightning and fire). | 3 dumps |
| F24 | **Sage scent bottles = `customSkillSlots` (VERIFIED on 5 of 5 picks, owner 2026-10-28).** Entry `{id, customId, state?, materialSlots[]}`, each slot `{index, optionIds[3], chooseOptionId, effectOptionIds[]}`. The owner confirmed the character is the Sage; current bottle (`state = CustomSlotState_Active`, `customId` 1) holds Scattered Spore, Husk, Prismatic Vine; the other bottle (no `state`) held Thunder Dragon Scale and Tumbleweed Seed. The picked ids are `1132`, `1232`, `1312` and `2121`, `2231`. Decoding: **the third digit is the position of the ingredient inside its category in tlidb order** (`_hero_traits.json`, Sage `ingredients`): `1132` = Damage #3 Scattered Spore, `1232` = Defense #3 Prismatic Vine, `1312` = Functional #1 Husk, `2121` = Special #2 Thunder Dragon Scale, `2231` = Functional #3 Tumbleweed Seed. The first digit is the bottle (`customId`), the second the slot (`index`); the slot's category is not stated but follows from its three option ids (the unchosen options still need no name to import: category + position gives the ingredient). The fourth digit differs by bottle (2 vs 1) and is unexplained. `skillPosRequirements.customSlotRequirementMap` ties a custom slot to a skill type. | read + owner |
| F25 | **Searched and NOT present in the dump:** mercenary/follower data (no key or text in any of the 34 top-level keys), `backupSkillDto` and `skillAdditionalAffix` (both empty), any destiny/kismet/ingredient/pactspirit **name**, and a `servantId` to name table. `tasks`, `functions`, `rewards`, `fashions`, `guideInfo`, `helpInfo`, `achievementInfos`, `growUpDto`, `SP3Base`, `userGem`, `otherInfo` and `SkillSlot` hold progression, shop or season-activity data only (`SP3Base` is a map-event state). | key-by-key read |
| F26 | **Belt blend (owner 2026-10-28).** The belt (slot 8) is Omni-Elixir Notes (`UniqueItmId` 113342, a tlidb legendary `internal_id`). Its `EnchantAffixs[1]` = `{Id: 3401001, source: 13}` and `EnchantSlots[1].affixId` carry the **belt blend**: `3401001` is the `modifier_id` of the tlidb blending-ritual line "Restores 3 % of Life on defeat" (talent 340002), which is what the owner reported. The belt also has `Status = FORGE_PRECISE`. `Bind` marks bound items (the ring). | read + owner + crawler capture |
| F27 | **tlidb `talent_id` equals the game `geniusId`.** 119 of 120 tree node ids (the miss is the prism core talent `80002000`), all 10 slate enchant talents, 13/14 base talents and all core-talent ids in the live dump are `talent_id` values in `tlidb-crawler/output/SS13/talent_tree/*.json`. That gives the **complete career-prefix table directly from data** (first two digits): 10 God of Might, 11 The Brave, 12 Onslaughter, 13 Warlord, 14 Warrior; 20 Goddess of Hunting, 21 Marksman, 22 Bladerunner, 23 Druid, 24 Assassin; 30 Goddess of Knowledge, 31 Magister, 32 Arcanist, 33 Elementalist, 34 Prophet; 40 God of War, 41 Shadowdancer, 42 Ronin, 43 Ranger, 44 Sentinel; 50 Goddess of Deception, 51 Shadowmaster, 52 Psychic, 53 Warlock, 54 Lich; 60 God of Machines, 61 Machinist, 62 Steel Vanguard, 63 Alchemist, 64 Artisan; 70 New God; 90/92 Nether King. `geniusCareerId` in the log is the same prefix (`1`=10, `4`=40; the two-digit ids are literal). This replaces the geometry-only F12/F13 matching (kept as a cross-check). The crawler's `column`/`row` are 1-based (`12060400` = column 6, row 4), Builder's are 0-based. | id join |
| F28 | **Pactspirit, destiny and follower ids are not in the crawler captures.** `pactspirit` and `destiny` outputs carry no id field (`modifier_id`/`term_id` only), so the id join has to be added to the crawler (section 10). Pet art names appear in asset-load lines (`Pet_SSR_RedUmbrella`, `DreamWeaver`, `EternalCaller`, `YuanBoShi`, `Swordsman`) but they are session scenery, not tied to a servant id. | grep + crawler output |
| F29 | **Destiny item ids follow the tlidb order.** Micro fates are `3500NN` and medium fates `3503NN` where `NN` equals the number in the tlidb icon name (`UI_S9Pet_SFate_1` = Micro Fate: Fire Resistance, `_3` = Lightning, `MFate_1` = Medium Fate: Fire Resistance). Observed and consistent with the owner's items: `350001` x2 (Micro Fate: Fire Resistance, owner has 2), `350003` (Micro Fate: Lightning Resistance, owner has 2; the second is not in the visible nodes), `350301` (value `13.0` = a medium fate; owner has Medium Fate: Fire Resistance). Micro values equal the top of the tlidb range (`7.0` of 5-7). Kismets are separate (`UI_S9Pet_Destiny3` = Kismet: Guillotine); their id range was not seen, so **Kismet: Guillotine is unresolved** and needs a login where its node is in the visible 30. Three of the six installed items remain unseen. | read + owner |
| F30 | **Followers/mercenaries (owner screenshot, Ajax, Iron Curtain).** The client calls them mercenaries internally (`SNMercenaryMain`, `SNMercenarySkillBag`, audio `UI_SN_Mercenary_Employ/Follow`; the English UI says Follower). Opening the panels in the second session logged only the page-open and audio lines, no data message: the only socket messages ever logged are `GetPlayerData` and `XchgSearchPrice`. The dump has no follower key. `player.FollowServant` (`11230`) is **probably not the follower**: it is identical in both logins, the id sits in the pactspirit id space (it is in the game's own pet red-dot id list, family 11), and pet-skin assets load many times in the same session. It is more likely the following pet. Unresolved; the deciding test is to change the follower in game, relog, and see whether `FollowServant` changes (section 10). The follower's skills (Tartarus: Life Tonic III, Shockwave Warcry III, Raging Warcry III) exist as normal skills in `_skills.json` (SS13 crosswalk game ids 7143, 7228, 7121) but none of those ids is in the equipped-skill set, so the dump never lists them. | read + owner screenshot |

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
| `customSkillSlots` option ids (`1132`, `2231`...) | 5/5 owner picks | resolved by structure: third digit = position in the tlidb ingredient category (F24) | resolved |
| Hero memory `BaseId` 71001–71003 | **3/3** | `_hero_memories.json memory_types[].internal_id` | resolved |
| Memory affix ids (`4021…`, `4022…`) | **12/15** | `crosswalk/SS13/memory-affixes.json rows[].compendium.gameId` | mostly resolved; the 3 `4031…` BaseAttrAffix ids miss (**GAP-4**) |
| Hero id (18001/1800) and trait ids (`1800011`...) | **0/4** | `crosswalk/SS13/hero-traits.json` `gameId` is null on all 27 rows | **GAP-5** |
| `geniusId` | **119/120** | tlidb `talent_id` in `output/SS13/talent_tree/*.json` (F27); the geometry rule (F12) is only a cross-check | **resolved by id** |
| Core talents (`bonusGeniusInfo`) | **all** | tlidb core-talent `talent_id` (`y=00`) | resolved by id; slot rule still HYPOTHESIS |
| Slate `BaseId` (`2603xx`, `2605xx`, `2610xx`) | **1/6** (only `394004` = Nether King's Judgement, tlidb `internal_id`) | base/legendary slates have no ids in `divinity_slate` | **GAP-6** |
| Slate talent ids (`BaseTalentList`, `EnchantTalentList`) | **13/14, 10/10** | tlidb `talent_id` (F22/F27); `90000061` (Nether King base) misses | resolved |
| `EffectTalentIds` (slate to node) | resolved by id | same `talent_id` join | resolved |
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
| GAP-8 pactspirit ids | map `servantId` to spirit. **Clean-source search:** tli-data and the crosswalk carry no servant id; the game's loose files hold ids only (`Local/AccountCache/*/NewPetRedDotData` lists ~148 ids, no names; the config packs are encrypted with no known key, `tli-decompiler/TLI_DATA_RECON.md`); no log line pairs an id with a name; the id digits are a grouping, not a name (F18). **Clean way to fill it:** observation by the owner (section 10), plus the crawler probing whether a tlidb pactspirit page shows an `id:` line the way legendary-gear pages do. Do not copy any third-party bundle table. |
| GAP-9 destiny / kismet ids | micro `3500NN` and medium `3503NN` follow the tlidb icon number (F29); kismet range unseen. Crawler: add the `id:` line or the icon-number-derived id to `destiny.json` once confirmed on one page |
| GAP-10 scent-bottle option ids | **resolved by structure** (F24): third digit = position in the tlidb category. No crawler field needed |
| F13/F16 | **resolved for the prefix table** (F27, from tlidb `talent_id`); core-talent slot rule still needs one more log (HYPOTHESIS) |
| Truncation (F5) | see section 9: lists are re-shuffled per login for skills, pacts and servants (merge logins), deterministic for talent trees (cut = the highest-id top-row nodes, at most 2 on 13 of 31 trees) |

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

1. Should the crawler/tli-data id work (section 10, now GAP-1 to GAP-9) be scheduled? It gates most of the long tail, and the tlidb talent id join (F27) already proves the approach.
2. Which import UX (section 11): the recommendation is a one-shot pick plus a re-import button, with desktop auto-detect as a convenience.
3. May the redacted fixture (`UE_game-redacted.log`) be committed as a test fixture? It stays out of git until answered (it lives in the gitignored `docs/local/`).

## 8. Owner experiments still needed (all small; each names the single thing it settles)

1. **Which field is the follower (F30)?** Change the follower in game (e.g. to a different one), log out to character select and back in, and copy the log. If `player.FollowServant` changes it is the follower; if not it is the pet. Also note which pet is set to follow, if any.
2. **Pactspirit names (section 10):** the naming runs below.
3. **Kismet ids (F29):** log out and in 3-4 times without restarting the game; each login re-shuffles `pointDatas`, so a visible Kismet: Guillotine node appears with about 45 % probability per login (about 85 % within 3). Then copy the log.
4. **Anything in the list below that you have not equipped yet and we have not seen:** an item with a **chip / extension**, a **tower sequence**, a vorax item, an **ethereal prism**, and a hero other than the Sage (to see `customSkillSlots` empty, and the hero-memory/trait ids of another hero).
5. **A talent tree with 31-32 nodes** (Warrior, The Brave, Ranger, Magister, Warlock, Prophet, Marksman, Elementalist, Artisan, Arcanist, Alchemist) with the top-row legendary nodes allocated, to measure the truncation cost directly (F5, section 9).

## 9. Truncation: what is lost, for whom, and what recovers it

The cap is 30 list elements; the 31st is written as `...`. Only the lists that carry **equipped** state matter (the owner does not need unequipped items). Measured on the live character (39 equipped skill items) and the three older dumps:

| List (equipped meaning) | Can exceed 30? | Order between logins | Typical endgame loss today |
|---|---|---|---|
| `bag.dressSkillItems`, `skills.skills`, `skillLayout` (skill and support objects) | **yes, for almost everyone**: 5 actives with an activation medium and 3-5 supports each plus 4 passives with 2-3 supports is about 36-45 items | **re-shuffled** each login | 3 of 39 objects missing in one dump (level and support rolls lost, name kept) |
| `geniusInfos[].geniusList` (talent nodes) | only trees with more than 30 non-core nodes: 13 of 31 trees (32 nodes: Warrior, The Brave, Ranger, Magister; 31: Warlock, Prophet, Marksman, Elementalist, Artisan, Arcanist, Alchemist) | **deterministic**, sorted by `geniusId` | 1-2 top-row (row 7, highest x) legendary medium nodes, same ones every login |
| `ContractInfosV2.pointDatas` (installed destinies) | yes: 6 areas x 11+ nodes | re-shuffled | about 45 % of nodes visible per login; installed destinies missed |
| `ServantInfos.servantData` (pact rank) | yes (owned list, 74 distinct ids over 3 dumps) | re-shuffled | rank unknown for about 4-5 of the 6 contracted spirits |
| `bag.dressingTalentBlocks` (slates) | no: at most 24 cells on the board (6 here) | stable | none |
| `bag.wearItems` (gear) | no: 10 slots | stable | none |
| `ContractInfosV2.ContractDatas`, `heroCharacterv3OverView` (3 memories, 3 traits), `customSkillSlots`, `bonusGeniusInfo` | no | stable | none |

Recovery routes, best first:

1. **(a) Names from `ItemChange` (always works, 100 %).** The post-login `ItemChange@ Add/Update Id=<BaseId>_<guid> ... PageId=-6 SlotId=n` lines are not capped and cover every equipped skill and support, including slot ids. We lose level, `SkillItemLevel` and support line rolls only for objects not in the dump. Gear and slates likewise (`-1`, `-4`).
2. **(b) Union the three skill lists inside one dump (reliability high, free).** `dressSkillItems` + `skills.skills` + `skillLayout` recovered 36/39 on the live account (`dressSkillItems` alone has 30/39).
3. **(c) Merge several logins (reliability high, cheap).** Two logins of the same character recover 39/39 skill objects (the logout-to-character-select then login cycle writes another dump into the same `UE_game.log`; the file also holds one dump per launch in the backups). For `pointDatas` and `servantData` each additional login adds a fresh random 30; with N about 66 nodes the expected share seen is about 45 % after 1 login, 70 % after 2, 83 % after 3, 90 % after 4 (installed destinies are the only part that matters). The importer should read every dump in every selected file, key objects by `Id`/`contractPointId`/`servantId`, and say how many logins it merged.
4. **(d) Talent trees (reliability partial).** Order is deterministic so relogging does not help. The tree layout is known from tlidb (`talent_tree`), so the importer knows exactly which 1-2 nodes were cut. Their prerequisites narrow them: in the older Ranger dump the cut nodes `43070400` and `43070500` have prerequisites `43060400` (3 points, allocated) and `43060500` (unallocated, so `43070500` cannot be allocated). So at most one open question per cut node; the importer can mark "unknown" and ask the user. Total spent points per tree is not in the dump (checked `player`, `SP3Base`, `SkillSlot`).
5. **(e) Owner experiments that might re-log a single item in full:** none found. The client logs `ItemChange` lines per equip event, but only the id, slot and count; panel opens (skill, pact, follower, talent) logged only UI and audio lines (F30). The only data messages ever logged are `GetPlayerData` and `XchgSearchPrice`. So there is no uncapped feed to find; merging logins is the fix.

What a typical player loses today (single login, no merging): all names, gear, slates, prisms, belt blend, scent bottles, hero, level, memories (complete); about 0-3 skill/support levels and rolls; 1-2 top-row legendary talents on 13 of 31 trees (unknown, not wrong); most installed destinies and pact ranks. After (b)+(c) with 2-3 logins: all skill levels and rolls, most destinies; talents still ask about the 1-2 cut nodes; rank is unknown only for spirits never visible.

## 10. ID spec: tli-data and crawler follow-ups (owner direction: store tlidb ids)

tlidb already exposes the game id on several pages and our crawler already captures it in a few categories. Measured joins (live dump, 6 equipped legendary pieces, belt, slates, trees; crawler captures `output/SS13` plus `data/seasons/SS14`):

| Category | Log field | Crawler/tli-data field | Join today | Follow-up |
|---|---|---|---|---|
| Talent nodes, core talents, slate talents | `geniusId`, `talentId`, `*TalentList` | `talent_tree[].talent_id` | **119/120, 10/10, 13/14** | none; persist `talent_id` in the season tree files (they already carry it in the raw capture but the shipped `trees` use column/row) |
| Legendary gear | `UniqueItmId` | `legendary_gear.internal_id` | **6/6 equipped + 7/7 earlier** | none |
| Legendary affixes, base implicits | `Prefix/BaseAffix/FixedBaseAffix Id` | `modifier_id` | **30/30, `FixedBaseAffix` 6/6**, `BaseAttrAffix` 16/25 | extend `modifier_id` to the 9 `BaseAttrAffix` misses (`4031...` memory stats, `1204...` prism) |
| Hero memories | `BaseId` 71001-71003 | `hero_memories.internal_id` | **3/3** | none |
| Belt blend / blending rituals | `EnchantAffixs Id` | `blending_rituals.modifier_id`, `talent_id` | **2/2** | none |
| Nether King slate | `BaseId` 394004 | `nether_kings_divinity.internal_id` | **match** (Judgment = 394004) | the other NK slates have `internal_id` too; add the base talent `9000006x` ids |
| Skills, supports, mediums | `BaseId` | `internal_id` (parser reads an `id:` line) | **null in all SS13 captures** although the crosswalk joins via Compendium ids | probe one skill page: if the `id:` line exists the parser misses it; fix the parser and persist `internal_id` |
| Gear base items | `BaseId` | none | 0/9 | `craft_base_type`/`craft_base_items` pages: probe for the `id:` line and capture it per base item |
| Crafted/rare affix ids | `Prefix/Suffix Id` (9-digit `104210001`...) | `craft_base_type` `modifier_id` (7-8 digits) | 0/32 after trimming 2-3 digits | probe whether the page exposes the 9-digit id per tier (`data-modifier-id` is attached to a line, may be a group id); capture both |
| Hero + trait ids | `heroPurchaseId`, `activeId` | none | 0/4 | hero trait page `id:` line; capture hero id and trait id |
| Divinity slates (base, legendary) | `BaseId`, `UniqueItmId`, `ShapeId` | `divinity_slate` (no ids) | 0 | capture `internal_id` and shape for every base/legendary slate kind |
| Prisms | `BaseId` 360620, affix `1204...`, `1234...` | `ethereal_prism` (no ids) | 0 | capture `internal_id` and affix `modifier_id`s |
| Pactspirits | `servantId` | `pactspirit` (no ids) | 0 | probe an `id:` line; otherwise observation (below) |
| Destinies / kismets | `tattoInfo.BaseId` | `destiny` (no ids) | 0 (but `3500NN`/`3503NN` match icon numbers, F29) | probe an `id:` line; add `internal_id` |

The third-party claim that tlidb ids equal the game ids is confirmed where the ids are captured (talents, legendaries, memories, belt blend, NK slate). For the others the crawler needs a probe on one live tlidb page per category before the field is specified; our captures do not keep the raw HTML, so I did not fetch live pages in this investigation. Spec for each category: persist `internal_id` (int, nullable), validate it against the schema, keep it out of public content that carries no id today, and extend `crosswalk` rows so `gameId` is filled from it rather than from Compendium.

**Pactspirit id table by observation.** The id space is unknown to us and the page may not expose it, so the owner's own panel is the ground truth. Procedure, cheapest first:

1. Log out to character select and in (no restart), copy the log: the dump gives ids for the 6 contract slots and `FollowServant`. Each login can test 6 spirits; the owner puts 6 known spirits in the 6 slots (all names are on screen) before logging out. **Six id-name pairs per relog.** The collection has 181 spirits; the owner owns at least 74 ids (union of 3 dumps), so about 12-13 relogs cover everything owned, each taking about a minute plus the slot rearranging.
2. Faster, if the in-game collection list is sorted by id: screenshot the whole collection page in default order. `servantData` gives the owned ids (union of dumps, 74+). If the visible order is monotone in id, align the two sorted sequences and verify with the six known pairs (`5330` Preserver, `18230` Kitty Express, `19230` Elixir Fairies, and three of the reserve). **One screenshot set plus 1-2 relogs** if it works; fall back to (1).
3. Each new player capture adds pairs for free if the importer asks users to name any unmatched spirit (opt-in), which keeps the table growing without owner work.

## 11. Import UX: options and recommendation (investigation only, nothing built)

**Decided by the owner (2026-10-28):**
1. **We never take or upload the log file.** The file never leaves the player's device.
2. **Web:** the log is parsed in the browser only (client-side), picker only.
3. **Desktop:** the player picks or auto-detects the log once, then the app offers an "update build" re-import when they relog.

Everything below is the investigation behind those decisions; the remaining tradeoffs are still investigation-only and nothing is built. Talent-tree truncation (section 9) is a confirmed real gap and stays a priority item.

Facts that decide it: the game writes `GetPlayerData` once per login and nothing else we can use (F25/F30); the dump lists are capped and re-shuffled per login (section 9), so **every extra login in the file improves the result**; the file is rewritten at every game launch with the previous one rotated to `UE_game-backup-*.log` (HYPOTHESIS for the rotation count: we saw one live file and two backups); post-login changes only update slot ids (`ItemChange`), never full objects; the file holds account ids and IPs (F19).

| Option | What it gives | Cost / risk |
|---|---|---|
| One-shot file pick (desktop and web) | Simple, privacy-clear, no background activity. Result is a snapshot of the last login in that file. | User must repick after relogging; picks only the dumps in that file. |
| Live watch (desktop) | Re-reads the file when it changes; picks up each new login dump automatically, so merging across logins (section 9) happens without effort. Slot-id changes between logins can be applied without a dump. | Needs a file watcher and a stored path; **it does not give live gear or skill rolls** because nothing writes full objects after login, so "live" really means "re-import on every login". Keeps a path (not content) on disk. |
| Auto-detect Steam library (desktop) | Zero-setup: read `libraryfolders.vdf`, look for `Torchlight Infinite\UE_game\TorchLight\Saved\Logs`. | Reads outside our sandbox, only a main-process feature, Linux/macOS paths differ; always offer the picker as fallback and show the path being read before reading. |
| Multi-file (backups) | Recovers more of the capped lists and an earlier character; lets the user choose which dump (name/level/hero label, no ids). | Backups hold other characters or old gear; must be shown newest-first with a chooser, and only the chosen dump merged for one character (match by `HeroId` + name). |
| Web, client-side parse | Nothing leaves the browser: `File.text()`, parse in memory, discard text, keep only the derived `Build`. Works with the same parser as desktop (pure TS). | Large files (42 MB seen): read in chunks and stop at the last dump, with a size cap; cannot auto-detect, picker only. |
| Real upload to a server | Allows server-side id tables and fixes without a client release. | Would send account ids and IPs; needs consent, retention rules and a redactor; no benefit for parsing, since the id tables can ship as data files. **Not recommended.** |

Privacy copy (draft): "Your log stays on your device. We read only the character block and ignore account ids, IP addresses and chat. Nothing is uploaded. Close the file picker to cancel; we keep no copy of the log." On relog the user must re-import (one-shot) or the app picks up the new dump (watch).

**Recommendation.** Ship the one-shot pick first on both desktop and web (smallest, safest, same parser), but design the parser to take a list of dumps and merge. On desktop add "auto-detect" as a convenience that only proposes a path and a "re-import" button that re-reads the same file (which is what "live" mostly buys); add a real watcher only if players ask for it. On web keep everything client-side. Surface an import report that says how many logins were merged, which lists were capped, and which items are unresolved (section 9). Do not build a server upload (decided above). The owner's desktop decision (pick or auto-detect once, offer "update build" on relog) supersedes the "only if players ask" watcher wording: a light watch that only offers the re-import is in scope for that flow.

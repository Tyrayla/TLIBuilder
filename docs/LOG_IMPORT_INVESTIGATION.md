# Importing a character from `UE_game.log` — investigation and design

Status: investigation only (2026-10-28). No product code. Spike scripts live in the
gitignored `docs/local/companion-log/` (parser, ID-bridge, grid-match); the log itself is never committed.

**Clean-room statement.** TLI Companion is source-available, not open source. Nothing here was
copied or derived from its code or its `game-ids` dictionary. Everything marked **VERIFIED** was
observed directly in one 2.9 MB capture (`UE_game.log`, 30,268 lines, one login) or by matching it against
our own hydrated tli-data (`npm run fetch:data`, SS14 + `crosswalk/SS13`). Everything marked **HYPOTHESIS**
was not proven by this single log. The three third-party write-ups were used only as leads, and every
claim from them that we rely on was re-checked below.

## 1. Verified format facts

| # | Fact | Evidence |
|---|---|---|
| F1 | The file starts with a UTF-8 BOM and uses CRLF. Decode as `utf-8-sig`, normalise `\r\n`. | first bytes `EF BB BF` |
| F2 | The login dump is one block: `----Socket RecvMessage STT----GetPlayerData----SynId = N` … `----Socket RecvMessage End----`. This log has exactly one (lines 22156–26751), preceded by a `SendMessage … GetPlayerData` with `+clientLang [en]`. | grep |
| F3 | The block's first line shares its line with the log prefix `[ts][frame]TLNetGame: Display: [Game] `; the tree body follows on the next physical lines (no per-line log prefix). | read |
| F4 | Tree syntax: each line is `|`-padding then one or more `+key` segments, optionally ending in ` [value]`. The **column of each `+`** is the nesting depth. Rule that parses all 4,595 lines: a line whose first `+` is at column *c* pops every open key at column ≥ *c*; its parent is the top of what remains; the rest of the `+key` segments on that line each nest one deeper. Lists are keyed `1,2,3…`. A key with a value has a trailing space in the key text (strip it). | spike parser, whole dump parsed, 33 top-level keys |
| F5 | **Every list is truncated at 30 elements**: the 31st is written as `+31+...` and the rest are dropped. Hit 20× in this dump (tasks, bag pages, skills, talents, pactspirits…). Any count-based logic must treat a 30-element list as "possibly more". | 20 `+...` markers |
| F6 | **No `+player` block and no name in this dump.** The top-level keys are the 33 listed in the brief. The character name is not in the log at all in this login path; the only names present are the platform account display name (`nickName`, lines ~20283) and numeric ids. `AttrUtils:SetPlayerLv = 1` is logged as a placeholder three times; the real level is the **last** `SetPlayerLv` after the dump (`= 94`, line 26766) and again as `_UpdateSceneLevel PlayerLv = 94`. | grep |
| F7 | The selected hero is logged outside the dump: `FightMgr@RoleType = 1800` and `Loading@ PreLoadHeroId = 18001`; the dump repeats it as `heroCharacterv3OverView.heroPurchaseId = 18001`. | lines 20904, 20931 |
| F8 | After the dump the client replays item state as `ItemChange@ Reset PageId=P` then `ItemChange@ Add Id=<ItemId> BagNum=1 in PageId=P SlotId=S` (and later `Update` for skills). Pages seen: `-1` gear (9 Adds), `-6` skills (36 Adds then 36 Updates), `-4` divinity slates (7), `-2`, `-10` (empty), `100–103` bags. The `Id` joins to the `+Id [...]` of an item object in the dump. | 269 lines |
| F9 | **All equipped items are fully described in the dump** even though bags are truncated: every `-1` (9/9), `-6` (36/36) and `-4` (7/7) `ItemChange` Id has a full item object in the dump. Bag pages 101/102/103 list 39/58/67 items via `ItemChange` but only 30 each have data (F5). Equipped-state import is therefore complete; "inventory import" is not. | cross-check |
| F10 | Gear slot ids (`wearItems[].Index`, `SlotId` on page -1), derived from the resolved base types: 1 helmet, 2 weapon, 4 chest, 5 amulet, 6 ring, 7 ring, 8 belt, 9 gloves, 10 boots (3 = off-hand, empty here). | resolved names |
| F11 | Skill slot ids (page -6): `1–5` = the five active skills, `s01` = that skill's activation medium (`101,201,…,501`), `s02…s0n` = its supports (`102–103`, `202–204`, `302–304`, `402–403`, `502–505`); `1001,1007,1013,1019` = passive skills with supports `1002–1003`, `1008–1009`, `1014–1015`, `1020–1021`. | resolved names; **HYPOTHESIS** for the exact meaning of the passive block until a second build confirms it |
| F12 | Talent grid: log `position{x,y}` ↔ TLI Builder `(column,row)` = **`(y−1, x−1)`** (transposed). 4 of 4 trees match a tree file's occupied-cell set exactly (25/25, 29/29, 30/30, 30/30). `geniusId` is the 8-digit number `PP·10⁶ + y·10⁴ + x·10²` (e.g. `40010300` = prefix 40, y=1, x=3), confirmed on all 120 ids against their `position`. | grid-match spike |
| F13 | Career prefix → tree: `4` = God of War, `42` = Ronin, `62` = Steel Vanguard (exact matches). `43` (the tree that holds the prism) matched Ranger and Magister equally because its 30-cell list is truncated; `43` ≙ Ranger is the **HYPOTHESIS** (first digit = god, second = hero index within the god). Other prefixes seen only as slate effect targets (`1x,2x,3x,41,6x…`) are unmapped. | grid-match |
| F14 | `talentBlockInfluence` is keyed by the slate's item Id and lists `EffectTalentIds`: the **talent nodes (as geniusIds) each slate slot overrides**. That gives slot→node targets for every installed slate, but not the slate's shape or position on the board. | read |
| F15 | A prism is `geniusInfos.info[n].prismInfo{geniusId, item}` + `prismEffectPositions`; the node under it has `inPrismArea=true`/`disable=true`. | read |
| F16 | Core-talent choice is `bonusGeniusInfo[n].value.geniusId` (e.g. `40001200` = prefix 40, "row 0", x=12). | read |
| F17 | Hero memories: `heroCharacterv3OverView.reminiscenceOverView.reminiscence[1..3]` with `BaseId` 71001/71002/71003, `BaseAttrAffix`, `BaseAffix`, `Suffix` arrays of `{Id, DynArgs[]}`. Hero traits: only `pointOverView.activeId = {1800011,1800021,1800031}`. | read |
| F18 | Pactspirits: `ServantInfos.servantData[]` = `{servantId, starLevel?}` — the **owned** collection (truncated at 30). No field in the dump says which are installed. | read |
| F19 | The log contains personal data: platform account name, `playerId`/`userId`/device ids, IP addresses, guild id, chat-free but account-bound progress. | grep |

## 2. ID bridge (this log vs our data)

Rates are unique-ids-hit / unique-ids-in-log, searched across every numeric value and numeric key in
SS12–SS14 + crosswalk (`docs/local/companion-log/bridge*.py`).

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
| Pactspirit `servantId` | **0/30 real** (4 numeric collisions with unrelated skill ids) | `crosswalk/SS13/pactspirits.json` `gameId` null on 175/175 | **GAP-8** (confirms the Migration note) |

**Bottom line:** equipped legendary gear, all skills and supports (by name), hero memories (mostly), and the
talent grid import with data we already have. Rare/crafted gear, support line rolls, hero traits, slates,
prisms and pactspirits need game-id fields that tli-data does not carry yet.

## 3. Mapping to the TLI Builder build model

Targets are the `Build` interface in `src/renderer/src/api/client.ts` and `KNOWN_BUILD_KEYS`
(`buildCompat.ts`). The frozen `tli1_` codec is untouched: an importer builds a `Build` object
client-side and hands it to the existing open/save path; it never edits `backend/build_code.py`.

| Log section | Fills | Quality |
|---|---|---|
| `bag.wearItems` page `-1` | `gear[]` (`EquippedGearItem`: legendary → `item_id` from `internal_id`; affix `DynArgs` → rolls; `Corrode` → `corrosion_type`) | legendary: full. rare/crafted: needs GAP-1/2; until then import as "unresolved item" with the raw text unavailable — **cannot be imported** |
| `bag.wearItems` page `-6` + slot ids | `skills[]` (`slot` 1–5 active, 6–9 passive; `supports[]` by `support_index`; `level`, noble `rank`) | names+levels full; support line rolls lost (GAP-3), so engine uses its tier-midpoint default |
| `geniusInfos` | `slots[]` (`TreeSlot.nodeStates` from `point`; `coreTalentSelections` from `bonusGeniusInfo`) | node points full for lists ≤30 cells; truncation (F5) drops the last cells of dense trees — **partial** |
| `geniusInfos…prismInfo` | `prisms[]/prismInventory[]` (`PlacedPrism` anchor from `prismEffectPositions`) | position yes; kind/rolls need GAP-7 |
| `dressingTalentBlocks` + `talentBlockInfluence` | `slates[]` | which nodes each slate hits (F14); **no** slate shape/orientation/anchor in the log → cannot rebuild board geometry |
| `heroCharacterv3OverView.reminiscenceOverView` | `heroMemories[]` | base type + 12/15 affixes today |
| `heroPurchaseId`/`activeId` | `traitId`, `traitSlotLevels` | needs GAP-5 |
| `ServantInfos` | `pactSpirits[]` | owned list only; installed set unknown (F18); fates/destinies not present in this log — cannot import. A second log with pacts installed is needed to know whether any block carries them |
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
* **No character name (F6).** Offer the dump by timestamp + hero + level instead of name; multiple dumps
  in one set of files are distinguished by timestamp and `playerId` (never display the id).
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
| GAP-8 pactspirit ids | map `servantId` ↔ spirit; crawler likely needs it from the in-game pactspirit page; otherwise players pick pactspirits manually |
| F13/F16 | one extra log from a different class/god to confirm career-prefix and core-talent rules |
| Pact destinies / installed pactspirits | a log from an account with pacts installed |

## 6. Implementation plan (follow-up tasks)

1. **Parser library** (M, ~2–3 days): pure TS module `src/renderer/src/importers/ueLog/` — decode, find
   dumps, bracket-tree parse (F4), `ItemChange` replay (F8), truncation flags (F5), level/hero extraction (F6/F7).
   Fixture-tested on a redacted copy of the log (strip player/account/IP lines). No UI.
2. **Skills + supports + level import** (S, ~1–2 days): `skills[]`, `characterLevel`, hero id, via the SS13 crosswalk
   `gameId` (data already present). Needs a data-loader that exposes `gameId`→skill.
3. **Talent grid import** (S–M, ~2 days): geometry rule (F12), prefix table (F13), core-talent selection;
   truncation warning.
4. **Legendary gear import** (S, ~1–2 days): `internal_id` + affix `modifier_id` + rolls + corrosion.
5. **tli-data/crawler fields** (L, owner decision — out of this repo): GAP-1…GAP-8. Unblocks rare gear,
   traits, slates, prisms, pactspirits.
6. **UI** (M, ~2–3 days): ImportPanel entry "From game log", report (found/partial/missing), privacy copy,
   multi-file handling.
7. **Hero memories + prisms + slates** (M each, after step 5).

Rough total for a useful "skills + talents + legendary gear + level" import: ~1.5–2 weeks; full
fidelity depends on step 5.

## 7. Open questions for the owner

1. A second log (different class/god, pact destinies installed, a non-truncated tree) would confirm F11, F13, F16.
2. Should step 5 (crawler id fields) be scheduled, since it gates most of the long tail?
3. Is a main-process "scan for the log" button acceptable for the Electron build (read-only, local)?

# What a UE_game.log contains

This note describes the fields found in one redacted `GetPlayerData` dump from a `UE_game.log`.
It is a practical inventory of that capture, not a complete schema for every message or game session.
The game can omit or cap sections, so a field may be absent even when the game tracks it.

## Fields that can describe a build

| Data | Fields seen in the dump | Builder import status |
|---|---|---|
| Character and season | `player.Level`, `HeroId`, `HeroPurchaseId`, `SeasonId`, and `heroCharacterv3OverView` | Character level is imported. The verified Sage Licorice Note selection and its selected advanced nodes are mapped. |
| Equipped gear | `bag.wearItems`, with item base IDs, slots, levels, and affix rows | Nine equipped items map in the representative capture. Ordinary gear and Vorax affixes resolve against the refreshed SS14 catalog. Unknown support modifiers and a few other data gaps remain visible in the import report. |
| Active and passive skills | `bag.dressSkillItems`, `skills.skills`, `skillLayout.slots`, and `SkillSlot` | Skill identity, level when present, and slot map. Multiple captures can recover entries omitted by log caps. |
| Support modifiers | Prefix and suffix rows on skill items | Support identity and slot map. Some roll IDs and ranks are absent from TLIDB data, so the draft reports those gaps and uses Builder defaults. |
| Talent trees and core talents | `geniusInfos.info`, including `geniusList` and `bonusGeniusInfo` | Logged node IDs map through canonical `game_id` values. Known nodes and ranks are applied to the matching Builder tree. Unknown IDs are skipped with a warning. |
| Slates and prisms | `bag.dressingTalentBlocks`; `geniusInfos.info[].prismInfo`, `prismEffectPositions`, and `prismGeniusId` | Base slates with a recognized shape import as editable slates. Their talent selections reuse talent-tree nodes by `game_id`, and core talent selections reuse the canonical slate pool by `game_id`. Nether King's Divinity (`BaseId` 394004) uses a dedicated three-cell footprint and two tree-node slots plus one Core Talent slot; its occupied-cell `Index` identifies the origin and resolves the corner orientation. The SS14 slate API has no unique-item catalog; known unique IDs 1003 (Fallen Starlight), 1005 (A Corner of Divinity), and 1010 (Pedigree of Gods) map to existing Builder kinds. Base ShapeIds 1033, 1035, 1043, and observed 1045 have explicit mappings; other shapes warn. Slate `Index` is an occupied cell encoded as `10*column+row`, not the piece anchor; placement is solved from the shape and direction. Ethereal Prisms join by item `game_id`, anchors by talent `game_id`, and `prismEffectPositions` maps `{x,y}` to Builder `{column:y-1,row:x-1}`. Logged allocations inside those positions become `boxAllocations["column,row"]`; `prismGeniusId` is preserved as the replacement talent ID. Unsupported affixes and unavailable rolls warn. |
| Pact spirits and contracts | `ServantInfos.servantData`, `ContractInfosV2.ContractDatas`, and `ContractInfosV2.pointDatas` | Contract slots map to canonical pact-spirit `game_id` values. Rank imports when it is present in the captured servant inventory; capped sections can leave rank unknown. |
| Follower selection | `player.FollowServant` | This identifies the cosmetic pet. The combat follower or mercenary selection is not present in the inspected player dump and is not imported. |
| Hero memories and trait state | `heroCharacterv3OverView.defaultReminis`, `reminiscenceOverView`, `pointOverView`, and `customSkillSlots` | Equipped memories, the Progress base-slot memory, verified Sage trait selections, and logged Scent Bottle ingredient choices import. Memory base-stat IDs use an owner-verified crosswalk in canonical tli-data. Ingredient option positions resolve through the Licorice Note ingredient catalog. |

The representative draft contains nine gear items, 37 skills and supports, character level, four talent
trees, memories, Sage trait state, logged bottle ingredients, and mapped pact-spirit contracts. Slate and
prism import uses the joins listed above. Unknown slate kinds or shapes and unsupported prism affixes appear
in the import warnings. Log truncation can still leave some skill details and pact-spirit ranks incomplete.

## Other account and game state

The same `GetPlayerData` dump contains information that does not describe the current build:

- **Account and session details:** `player.Name`, `player.PlayerId`, `player.UserId`, `player.ChannelId`,
  `player.ActualActiveTime`, and `player.CurrentMapPoint`. These can identify an account or describe recent play state.
- **Cosmetics:** `fashions.infos` includes owned and equipped fashion records.
- **Progress and rewards:** `achievementInfos`, `growUpDto`, `tasks`, `rewards`, `guideInfo`, and `helpInfo`
  include completion, unlock, reward, and tutorial state.
- **Currency and purchases:** `userGem` and parts of `otherInfo` include currency or payment-related state.
- **Map activity:** `SP3Base` includes current map, activity, card, item, and map-affix fields.
- **Social and feature state:** `guild`, `ServantPickInfos`, `functions`, `ForbidFunctions`, and
  `gmForbidFunctions` describe guild, selection, or feature availability.
- **Skill resources and custom slots:** `SkillSlot`, `customSkillSlots`, and `skillPosRequirements` describe
  resource costs and custom slot configuration.

The current Builder importer scans `GetPlayerData` payloads for build-related fields. It does not import
the unrelated account, payment, cosmetic, progression, or map state listed above. It reads selected files
in the client and does not upload or save the log.

## Records outside the player snapshot

The wider log also has message headers and state-change lines. Across the logs audited so far, these
include:

- **Request and response framing:** `SendMessage` and `RecvMessage` entries carry message names,
  timestamps, frame numbers, and a sync identifier. The audited data responses are `GetPlayerData` and
  `XchgSearchPrice`. The latter's payload has not been mapped in this investigation.
- **Inventory changes:** `ItemChange` lines report a reset or an item add or update, with an item ID,
  page, slot, and count. They can confirm where an item sits, but they do not repeat its full affix and
  roll data.
- **Session and load state:** other lines report the loaded hero and player level. These can help when a
  `GetPlayerData` dump lacks a `player` section, but they are not full character records.
- **UI events:** opening some skill, pact, follower, and talent panels produced UI or audio log lines,
  but no additional data response in the captures reviewed.

The log is sensitive even when it contains no chat. The audited files include account names and IDs,
device IDs, IP addresses, guild IDs, and account-bound progress. Redact these fields before sharing a log.

## Limits of this inventory

This inventory comes from one redacted player-data capture. It does not establish which message types
appear in every log, whether every listed field is present for every character, or how fields change
between login, map changes, and other events. A broader field map needs additional captures from those
states. See the [UE log import audit](LOG_IMPORT_INVESTIGATION.md) for the current build-field mappings
and unresolved TLIDB IDs.

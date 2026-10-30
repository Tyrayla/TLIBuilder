# What a UE_game.log contains

This note describes the fields found in one redacted `GetPlayerData` dump from a `UE_game.log`.
It is a practical inventory of that capture, not a complete schema for every message or game session.
The game can omit or cap sections, so a field may be absent even when the game tracks it.

## Fields that can describe a build

| Data | Fields seen in the dump | Builder import status |
|---|---|---|
| Character and season | `player.Level`, `HeroId`, `HeroPurchaseId`, `SeasonId`, and `heroCharacterv3OverView` | Level and skill selection appear in the draft. Hero selections and related settings are reported as unmapped. |
| Equipped gear | `bag.wearItems`, with item base IDs, slots, levels, and affix rows | Nine equipped items map in the representative capture. Ordinary gear and Vorax affixes resolve against the refreshed SS14 catalog. Unknown support modifiers and a few other data gaps remain visible in the import report. |
| Active and passive skills | `bag.dressSkillItems`, `skills.skills`, `skillLayout.slots`, and `SkillSlot` | Skill identity, level when present, and slot map. Multiple captures can recover entries omitted by log caps. |
| Support modifiers | Prefix and suffix rows on skill items | Support identity and slot map. Some roll IDs and ranks are absent from TLIDB data, so the draft reports those gaps and uses Builder defaults. |
| Talent trees and core talents | `geniusInfos.info`, including `geniusList` and `bonusGeniusInfo` | The parser retains logged allocation IDs. The five-digit IDs in the representative capture do not match TLIDB's `talent_id` values, so those allocations are not applied. |
| Slates and prisms | `bag.dressingTalentBlocks`, `prismInfo`, `prismEffectPositions`, and `prismGeniusId` | Placement and effect data can be present in the log. Slate and prism base identities do not yet have reliable TLIDB joins, so they are not imported. |
| Pact spirits and contracts | `ServantInfos.servantData`, `ContractInfosV2.ContractDatas`, and `ContractInfosV2.pointDatas` | The dump contains servant and contract IDs. Available TLIDB pages do not expose matching IDs, so the importer leaves this state out and reports the limitation. |
| Follower selection | `player.FollowServant` | The field is present, but the logged ID does not match a TLIDB follower `game_id`; the importer does not apply it. |
| Hero memories and trait state | `heroCharacterv3OverView.defaultReminis`, `reminiscenceOverView`, and `skillOverView` | The dump has related state, but the current importer does not map it into the draft. |

The representative draft contains nine gear items and 37 skills and supports. The game log also marks
17 sections as truncated in that capture. The preview reports those limits before the user imports.

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

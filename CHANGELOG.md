# Changelog

## [Unreleased]

### Mobile
- **Tap-to-remove toggle for the talent tree.** On phones there's no right-click, so removing a talent point meant a long-press — which also opened the node tooltip and felt awkward. A new mobile-only toolbar toggle flips a node tap between adding and removing points, so deallocating is now a single tap (with the same cascade behavior as a desktop right-click). Desktop is unchanged (left-click adds, right-click removes), and the toggle auto-resets if you widen back to desktop.

## [0.6.3] - 2026-08-06

### Mobile
- **The build sidebar becomes an overlay drawer on phones.** At 768px and below the persistent sidebar is replaced by a fixed drawer with a floating toggle, a dimmed backdrop, and auto-close on navigation, backdrop tap, or Escape; opening a build shows the drawer so its navigation is reachable. Settings and Loadout overlays were lifted out of the sidebar shell (a transformed ancestor had been dragging fixed modals along with the drawer), and every modal is now capped to the viewport width so nothing spills off-screen. Desktop is untouched — the responsive rules only apply at phone widths, and the Electron window never gets that small.
- **Every screen now stacks cleanly on a phone instead of squishing.** Config, Gear, Skills, Hero Traits, the tree screens, Slates, and Pact Spirits lay out at natural height as a long scroll rather than cramming their internal sections side-by-side; the talent and Dance of the Deep trees render full-size with touch pan, slate cells own their drag gesture so placing works by touch, and the pact-spirit picker gains a close button.

### Talent trees
- **The tree selector now shows each god's icon.** God/goddess selector cards and the slot-rail slots carry full-bleed tree art behind their text (with an accent-tinted scrim for legibility), and the static points display is now a real fill meter — purple as you allocate, amber once you pass the cap.
- **Shared, consistent screen headers.** The tree selector and tree viewer now use one `ScreenHeader` component, fixing headers that had drifted apart in padding and cards that visibly resized when moving between the two screens; a border seam at the sidebar/header corner and the tree card's Remove/Shift button widths were also corrected.
- **Selena's Dance of the Deep tree is back to its authored layout.** The trait had regressed to a generic flat node list during an earlier data recrawl; its real tree-allocation topology is restored (and the flat-schema fallback now warns loudly instead of silently degrading), with the Dance Step sub-variants — Crimson Dash, Agonizing Revival, Eternal Sleep — corrected in the glossary. As in 0.6.0, the trait is browsable but still not DPS-modeled.
- **SS13 post-launch data refresh.** A live re-crawl brings in the real Dance of the Deep tree data and icons (replacing a pre-release placeholder), pact-spirit and ethereal-prism icon/affix corrections, a Memory Revival rebalance, and Sweet Dream / corrosion-base content changes across 38 craft base types — the last of which had never had a working import path.

### Preview Mode
- **Preview Mode is now a display toggle inside the normal app, not a separate stripped-down shell.** Previously entering preview bypassed the persistent sidebar entirely; now the sidebar always renders (showing empty slots in preview, never touching your real build), the Preview button turns into an active Exit Preview control that returns you to wherever you entered from, and identity comes from a subtle diagonal watermark on the tree canvas. Allocating a node while previewing provably never reaches your saved build.

### Build management
- **Build cards and the sidebar now show character identity.** A build card reads e.g. "Lv 100 Selena — Dance of the Deep" (hero trait in gold) instead of a list of tree names, and the same identity line sits above Save / Save As — so imported builds, whose share codes carry no name, are finally identifiable at a glance. It degrades gracefully to level-only while the catalog is still loading or for an unknown trait.

### Loading & gear editor
- **Real loading states everywhere.** A shared spinner replaces the drifted placeholders that used to imply the wrong thing while data loaded — the tree selector's hardcoded card grid, Skills' false "no results", Gear's "0 items" header and inert rows, and the empty pact-spirit board — and every load path now has an explicit failure branch, so there are no stuck spinners and an empty result is never mistaken for a loading one. A new bottom-left load-progress pill fills as each catalog settles and then fades to "Loaded".
- **Gear editor actions and custom item names.** The gear editor now carries Rename, Duplicate, and Remove actions alongside Save/Cancel, and you can give an item a custom display name (up to 60 characters) that shows in equipment slots, Items in Build, and note mentions while the editor, preview, and tooltips keep the true name. The name survives save, duplicate, and the share-code round trip — carried additively through the frozen build code, so builds without a renamed item still encode byte-for-byte identically. The editor column is now a fixed viewport-derived width, so opening it no longer shifts the layout.

### Engine & DPS
- **The Crit Multiplier breakdown now attributes every source of Crit Damage.** It previously summed a stat key that doesn't exist, so it only ever showed the 150% base — your gear, tree, support, and base Crit Damage sources are now all itemized. Tyrant's Iron Fist's "Crit Damage per Mana consumed recently" is likewise now folded into the real Crit Damage pool with a labeled "Mana Consumed" source. Computed values are unchanged (byte-identical goldens); this is a reporting fix.
- **Crit Rating per Mana consumed gets the same treatment** — Tyrant's Iron Fist's Crit Rating bonus now shows a labeled Mana Consumed source in the Crit Rating breakdown instead of being folded in silently, again with no change to the resulting crit chance.
- **Per-Mana affixes now badge Consumed instead of Inactive.** Compensatory Life (spell-damage-per-mana) and mana-regen-per-mana-consumed affixes were contributing but showing an Inactive badge; they now correctly read Consumed. Badge-only — no DPS changes.

### Fixes
- **Fixed a crash that could wipe unsaved build progress.** A real user lost all in-memory work when rapid place/remove clicks on a legendary slate briefly desynced the slate's view of a slot, and — with no error boundary anywhere in the app — a single uncaught render error unmounted the whole interface. Fixed in two layers: every persisted-key lookup in the slate screen is now guarded, and a root error boundary catches anything that still slips through, offering recovery that generates a real build code (or raw JSON download) from the untouched in-memory build so your progress is never lost to a render crash.

### Security
- **Backend hardened against path traversal and DNS-rebinding** (from an owner-reviewed security scan). Season-tree file reads/writes and the untrusted slate slug are now normalized and traversal-guarded (CWE-22), and a Host-header check rejects non-loopback requests on the network path while leaving the in-process web build's worker dispatch exempt (CWE-352). Full backend suite green.

### Project
- **The app is unchanged for users, but the game dataset now lives outside the public repo.** `data/` is no longer tracked in the source tree; it's pulled from a private source at build time, and the CDN that serves the web build's data now enforces an origin allowlist. The application code stays MIT-licensed, while the game dataset carries its own separate terms (`DATA-LICENSE.md`).

### Under the hood
- Dead-code cleanup (Phases 1–5): removed the deprecated legacy compute chain, ~18 unused API endpoints and their client wrappers, the orphaned form-upload IPC chain (and the `python-multipart` dependency), and a batch of zero-caller Python symbols, the hand-curated `node_modifier_pool`, and the retired manual tree-editing surface. Live compute path untouched; goldens byte-identical.
- Added a GitHub Actions CI workflow (typecheck, vitest, pytest, plus a skip-count guard).
- Added a Playwright E2E harness covering both the web (dist + Pyodide) and Electron targets.
- Desktop packaging fixed to positive file globs and prod deps trimmed to `electron-updater`, cutting the packaged app from ~123MB to 3.9MB.
- Trimmed the web bundles (`backend-py.zip` 596→498KB, `engine-data.zip` 1.8→1.1MB) and switched the data zip to content-hashed immutable caching.
- Fixed a cross-drive relative-path crash in a test fixture index on Windows CI.

## [0.6.2] - 2026-07-24

### Theme & readability
- **App-wide theme overhaul.** The interface moves to a cool blue-grey ("Steel+") palette built on a single 8-step surface ramp, replacing the patchwork of hand-picked dark blues and purples that had accumulated across screens. The practical change: the page background is now the *darkest* surface and panels sit above it, so cards read as raised rather than as holes punched into the background.
- **Panels are actually panels now.** The stat boxes on Calcs and the category cards on Config previously had no background of their own — they were a faint hairline over the page, so nothing read as a container. They now carry a real fill with a distinct header strip, separated by contrast rather than by outlines, which removes the boxed-in grid look.
- **Text is white-led.** Body text moves to near-white with a single neutral grey scale beneath it, retiring the mix of lavender and blue-grey tints that made labels look muddy. Config's toggle labels in particular were rendering at a muted-label tint despite being the screen's main content.
- **Talent tree is legible.** Unallocated nodes were nearly invisible against the canvas (about 1.13:1 contrast — you were effectively reading the rings alone); nodes now sit at roughly 1.87:1 and read as filled chips. Connector lines, column labels, and locked-node text were retuned to match.
- **Tree selector columns carry their god's colour.** Each column's identity colour tinted only a 6px strip at the top, so a column scanned as a grey card with a stripe. The colour now runs through the whole card, with the selected tree brightest in its column and selection outlined in the column's own colour.
- Buttons share one shape across variants — Reset, Reselect and Add Prism were each hand-styled with their own palette and read as controls from three different applications.

### Skills
- **Focus and Spirit Magus skills are now correctly allowed in active slots** when your build enables it — Steel Vanguard's "Knowledgeable" core talent (resolved from all five grant paths: tree slot, slate, legendary bracket affix, belt blend, and ethereal prism) and Iris's Vigilant Breeze / Growing Breeze base traits. Previously both were flatly excluded from the catalog regardless of build state.
- **Turning off the enabling talent no longer strips your setup.** A skill parked in a slot it's no longer permitted in stays equipped and shows a per-slot error badge and banner, but contributes nothing — no damage, no stat contribution, no reservation. The same applies on import.
- Support levels are quicker to set, and level selectors sit consistently at the top of their panel.

### Import / Export
- **The importer now says plainly that Torchlight: Infinite's own in-game build codes aren't supported**, in both the hint and the failure message, and mentions that share links work — which the importer has always accepted but never advertised.
- **Importing with unsaved changes asks about your work only once the import is known to be viable.** Previously the "Save before importing?" prompt appeared before the pasted code had been validated at all, so an unusable code still made you decide about unsaved work for an import that was always going to fail.

### Verification Database
- New entries for **Ill Omen + Reap Purification** and **Torturer's Touch (Affliction + Reaping)** (research capture, unverified).
- New entries covering the slot rules above, including the **Iris slot-2 "no attacking or casting action" restriction**, which is deliberately *not* modeled — Dazzling Bloom, the common pick for that slot, contradicts the predicate the description implies. Recorded as an open verification item rather than guessed at.

### Fixes
- Fire damage-type text now clears WCAG AA contrast on the new surfaces.
- The hero-trait active checkmark badge is scaled to match the allocation badge.
- Line endings are normalised via `.gitattributes`, ending the CRLF churn on generated verification docs.

## [0.6.1] - 2026-07-16

### Talent trees
- **Passive tree visual-clarity pass**: node bodies now fill as an allocation meter, connectors light or dim based on whether their prerequisite is satisfied, and hovering previews what a click would do — the auto-allocate path in green, or a right-click cascade-deallocate in red, each showing point cost and DPS delta in the tooltip.
- **Talent-point counters** — per-tree allocated points now show on the slot rail, alongside a global total against the 115-point budget with a warn-only over-budget state (the 115 cap is an assumed in-game max, pending verification).
- **Hero trait tree enlarged** — bigger nodes and allocation badges, taller canvas.

### Engine & conditions
- **SS13 Afterlight engine fixes**: Chromatic Shot, and the Licorice Note / Unsullied Blade / High Court Chariot hero traits, now read their values from the season catalog instead of hardcoded SS12 numbers — several had silently drifted (all over-reporting DPS) since the SS13 rollover. Chromatic Shot's shots-on-target shotgun cap had also gone silently dead under SS13's new Physical-based version of the skill (measured ~49% DPS overstatement on an affected build). Spell Burst's SS13 trigger-wording change ("activating" → "consuming") is now recognized, restoring three mechanics (Squidnova grant, mana loss, Life/ES restore) that had silently stopped firing. Modeled the 4 new SS13 Condensed supports (Physical→element conversion).
- New **"Have Been Hit Recently"** condition toggle — "(haven't) been hit recently" gear/pact-spirit lines now resolve properly (Preserver of Eternity's Graceful Pace Movement Speed wired to stats; SS12 Injury Buffer and SS13 Deflection lines recognized).

### UI
- **Build-select screen toolbar regrouped** — create actions (Import Code / New Folder / New Build) are now a single cluster, Dev Tools is tucked into a corner, and Select is a checkbox toggle.

### Fixes
- **Fixed Dance of the Deep (Selena) builds losing their allocated trait-tree nodes on save/reload.**
- Fixed a crash opening the talent tree (hooks called after an early return).
- Fixed the Skill panel showing raw crawler-mangled text (most visibly Mana Boil's consume line — now correctly "Consumes 3% of Max Mana every second"); skill overrides now apply to the skill list/tooltips, not just DPS computation.

## [0.6.0] - 2026-07-15

### New Season: SS13 "Afterlight"
- **SS13 "Afterlight" is live** — full new-season data: new and rebalanced skills, legendary gear, pact spirits, talent trees, and hero traits, plus the new **Nether King** god talent tree and its Divinity slate data.
- **Nether King's Divinity slate is fully craftable** — all 92 talent nodes are selectable and appear correctly in the slate picker (fixed a same-day issue where a name-collision bug had silently collapsed 88 of the 92 nodes down to a handful of duplicates).
- **Glossary expanded** for the new SS13 mechanics, including newly-added Dance of the Deep terms sourced directly from the game database.

### Hero traits
- **Selena — Dance of the Deep**, Selena's SS13 hero trait, is now browsable and selectable: its node tree, Dance Step and its Crimson Dash / Agonizing Revival / Eternal Sleep variants, Activation Medium: Terra, Crimson Tide/Shade, and more are documented in the in-app glossary. **Its DPS is not yet modeled** — too many interlocking unknown mechanics (Crimson Tide, Dance Step/Eternal Sleep, Crimson Shade summons, Ominous Curse, Terra Charge, Catalyst: Ground) to model accurately yet. Selecting it has no effect on computed stats; tracked in `data/verification/dance-of-the-deep.json` (status: unverified).

### New skill mechanics
- **Shadow Strike** — the engine now models Thunder Spike's Shadow-summoning mechanic: N Shadows repeat the player's own attack against a target, with each Shadow beyond the first dealing reduced damage (the game's Shotgun Effect falloff, confirmed flat rather than compounding via in-game testing); the player's own hit is unaffected. Shadow sources are wired from Haunt, Frantic Shadow, Despised Shadow (its 33%-chance-for-extra-Shadows roll, correctly gated to manual use only — it doesn't proc off Rhythm/Instruction-triggered casts), and a Ronin talent node.
- **Thunder Spike** is now a fully modeled skill: 205%→277% Weapon Attack Damage, a full Physical→Lightning conversion, and an inherent Numbed application on hit with an in-game-measured uptime formula. Both Shadow Strike and Thunder Spike were validated against in-game Recount testing and moved from unverified to partially confirmed in the Verification Database — see `data/verification/shadow-strike.json` and `data/verification/thunder-spike.json` for the full write-up, including a couple of remaining unmodeled edge cases (Numb Magnificent's shadow-hit-count proc chance, Everburn Thunderfire on Thunder Spike specifically).
- **Damage over Time (skill-DoTs)** — the engine now models the ongoing tick damage of skills that deal Damage over Time directly, rather than only a skill's Hit component. First two skills: **Mind Control** (Erosion) and **Path of Flames** (Fire). Validated against the training dummy to within ~±10%; treat DoT DPS numbers as an estimate for now. Type-matched "X Damage" sources and "Elemental Damage" now correctly scale a matching skill-DoT, and above-max-skill-level scaling applies to DoT the same way it applies to Hit damage.
- **Split Shot** — new skill with four supports, including Collaboration and Rapid Advance's channeled-transform behavior.
- **Spell Burst** completed end-to-end: Squidnova's buff, skill area, sustain, and kismet interactions are wired; **Lucky/Unlucky** critical strikes are modeled (Perched River kismet), with your true (uncapped) crit chance surfaced in Calcs.
- **Tangles**: per-Tangle modifier scaling and Magister's generate-Tangle nodes are now wired.
- New activation-medium roll system built around **Wind Rhythm**, plus the **Demolisher** and **Groundshaker** skills.

### Minions
- **Minion DPS is now modeled** — a dedicated minion engine (Spirit Magus, Thunder Magus, and more) covers minion Multistrike, Empower, per-skill scaling, and supports attached to a minion, mirroring the player damage model.
- **Known limitation:** SS13 minion base values are a stopgap carried over from SS12 pending fresh in-game measurement of the new season's numbers — treat minion DPS as provisional until re-measured.

### Sustain: Mana/Life consumption and recovery
- New **Restoration** engine — Regain, Regen, and effective-HP (EHP) now feed a dedicated recovery/sustain display, alongside a steady-state Life%/Mana solve ("Stable Life").
- Per-skill mana/life cost is now modeled and folded into sustain, including intrinsic cost conversions (e.g. Bull's Rage's mana-to-life conversion) and Compensatory Life.
- **Elixir system** — scent-bottle buffs scaled by Elixir Effect, including Licorice Note (Sage hero trait) ingredients and cross-apply.

### Gear, hero memory, and talents
- **Editable roll values** — click a number in the gear or hero-memory editor to set an exact roll instead of only dragging a slider.
- Hero memory gets **searchable affix dropdowns** and per-slot-type affix lockouts, with combo-mod tiers grouped under one modifier.
- **Fate/Kismet roll values** are now settable exactly, with roll ranges shown in the UI instead of just the midpoint.
- **Path allocation** — clicking a distant talent node now fills in the prerequisite chain to reach it, instead of requiring each node in between to be clicked individually.
- **Gear corruption edits are staged** instead of applying live, so you can back out before committing.
- Fixed: a "+X% Max Life and Max Energy Shield" gear affix that fed only Energy Shield; negative-range affix parsing that failed to show a slider; a missing base-item implicit when a legendary omits it; a Max Life + Energy Shield combo that dropped the Life half; Additional Life/Mana/Energy Shield/Armor/Evasion now correctly multiply per source instead of summing.

### Build management
- **Build folders** — the build select screen now supports folders: create, rename, nest arbitrarily deep, and delete (deleting a folder moves its contents up to the parent). Navigate via folder cards plus a breadcrumb.
- **Drag-and-drop**: drag builds into folders, onto breadcrumb segments to move them up a level, or between cards to reorder; folders drag the same way. Manually reordering a folder keeps your custom order; otherwise builds sort by most recently saved, newest at top (build files now carry created/updated timestamps, falling back to file time for older builds).
- **Bulk delete** replaces the per-card Delete button: hit **Select**, check builds, then **Delete (n)** with one confirmation — plus a **Move to…** bulk action.
- Folder layout is stored locally in a `folders.json` next to your builds; share codes are unaffected. New `GET`/`PUT /api/builds/folders` backend endpoints persist it.

### Verification & reference
- New **Verification Knowledge Base** — searchable in-app (Verification Database, main menu) and in `docs/verification/`, tracking confirmed in-game behavior and modeled-but-untested coverage for every mechanic, cross-linked to the in-app glossary.
- **DPS-coverage badges** (Full / Partial / None) now appear across skill, support, and gear catalogs, so what's fully modeled is clear at a glance.
- Reference browser: 3-mode tabs, click-through glossary/Help DB terms with navigation history and colored links.

### Fixes
- **Extended Duration support is selectable again** — a long-standing bug gated it off every skill.
- **Rhythm activation medium's movement-damage rate is now tier-correct**: the per-meter bonus was hardcoded to a flat 3% at every tier; it's now sourced per-level from the crawled data (3% / 3% / 2% / 2% for levels 0–3), correcting a prior overstatement at tiers 2–3.
- **"Cannot inflict Numbed"** no longer overrides a manual Numbed toggle — it now only suppresses the engine's automatic application, matching how Frostbite already behaves. (Only affects builds with both a manual Numbed toggle and a "cannot inflict Numbed" source active.)
- Importing a malformed or too-new build code now shows a clear error message instead of failing silently or crashing.
- Ailment-damage additional and crit-strike supports no longer inflate hits they shouldn't apply to; per-N-consumed gear lines no longer inflate stats; fixed gear implicit double-counting and weapon+shield attack-speed averaging; channeled Split Shot now fires at the correct smooth attack rate.

### Security
- **Renderer hardened against XSS**: all HTML rendering (including update-notes display) now runs through a shared sanitizer with an allowlist, closing a path where a malicious changelog/release-notes entry could have run arbitrary code; external links now open with `rel="noopener noreferrer"`; added clickjacking protection headers to the web deploy.

### Known limitations
- **Selena's Dance of the Deep and the new Terra skills** are selectable but not yet DPS-modeled — SS13 in-game data for these mechanics is still being gathered.
- **SS13 minion base values** are an SS12 stopgap pending re-measurement against the new season.

---

## [0.5.5] - 2026-06-26

### New skill
- **Chromatic Shot** with its canvas supports **Lightchaser** (Magnificent) and **Splendor** (Noble) — compulsory damage-type conversion (a random element each cast, modeled as the expected average across Fire/Cold/Lightning), shotgunning projectiles with a per-element damage breakdown. Validated to within ~0.5% of in-game.

### Cast-speed breakpoints
- **Tangles** now follow the game's whole-tick **cast-speed breakpoints** (30 ticks/sec): the Tangle panel shows ticks-per-cast and tells you exactly how much **Increased or Additional** cast speed reaches the next breakpoint.
- **Spell Burst** breakpoint helper now shows both the Increased and Additional speed needed (charge speed, or cast speed with Play Safe), combining the labels when both reach the same breakpoint.

### Config
- **Auto-inflicted conditions** your build guarantees (e.g. Splendor inflicting Numbed/Frostbite/Ignite, and the derived Frostbite Rating) now appear in Config automatically, tagged with their source. A new Settings toggle locks them or leaves them editable.
- Cleaner numeric inputs — no more clunky "/ max"; the cap shows on hover. "Shots on Target" is now **Projectile Hits** and tracks your projectile count.

### Performance
- **Much snappier** stat updates: disabling an aura, or opening a skill/support catalog, no longer lags — the headline DPS updates immediately and the catalog's per-item comparisons are batched into one request. Season data is now cached, making bulk computes ~3.6× faster. (Big win on the web version too.)

### Fixes
- Running the dev and installed app at the same time no longer cross-wires their saved builds (separate backend ports).
- Importing a current build no longer shows a bogus "older version" warning.
- **Erosion is no longer treated as Elemental** for "on Elemental hit" effects — Elemental is Fire/Cold/Lightning only.

## [0.5.4] - 2026-06-26

### Hero traits
- **Fixed missing nodes** — several hero-trait nodes weren't showing up at all (e.g. Wind Stalker's Cat's Punches, Incarnation of the Gods' Incarnation, Frostbitten Heart's Glacial Night, Zealot of War's Ceasefire/Extreme Heat/Eternal Flames, Creative Genius's Auto-Ingenuity Program & Multi-Coupling Equation, and more). All recovered.
- **Cleaner node layout** — levels now line up consistently (a single-option level no longer floats higher than the others), guaranteed/always-granted nodes are shown on top, and per-rank nodes show only the **selected rank** in their tooltip instead of every rank at once.
- **Creative Genius** now displays its real structure: a guaranteed node plus separate pick groups per level, shown as combined "pick one" bubbles that fan out to the options when clicked (with the chosen option's tooltip on hover).
- **Community trait names** — the hero-trait dropdown now shows each trait's community shorthand (e.g. "Thea 1", "Bing 2") and is **sorted by release order**.
- **Cat's Punches** (Wind Stalker) is now calculated — its Initial Multistrike Count scaling and additional damage are modeled.

## [0.5.3] - 2026-06-26

### New damage mechanics
- **Spell Burst** — eligible Spells charge up and auto-recast in a burst, modeled on the game's 30-per-second server tick, with manual vs. auto-trigger handling and per-support burst-damage bonuses.
- **Tangles** — the Spell Tangle skill type: your spell is cast by attached tangles, with Tangle Damage, Tangle Damage Enhancement, attached count, and Dormant Entanglement.
- **Curses** — curse application from skills and gear, per-type damage-taken amplification scaled by Curse Effect, a curse limit with an over-limit resolver, and per-curse breakdowns.
- **Empower skills** — Euphoria buffs from slotted Empower skills scaled by Empower Skill Effect, including Well-Fought Battle and Mass Effect.
- **Channeled skills** — a channeled-DPS framework (stack ramp and refresh) plus two new modeled skills, **Icebound Beam** and **Howling Gale**, and their canvas supports.
- **Multistrike** — full attack-speed and chain model.

### Hero traits
- **Erika** — Lightning Shadow (Numbed).
- **Rosa** — High Court Chariot (No Guard, Block Ratio, Holy Domain).

### Build management
- **Web version** — TLI Builder now runs in the browser at **tlibuilder.com**; your builds save locally in the browser.

### Config screen (was Conditionals + Calcs)
- Renamed **Stats → Calcs** and **Conditionals → Config**, with the old Calcs page folded in.
- Conditions now **auto-hide** unless your build actually uses them — toggle **Show all** to see every option.
- **Editable enemy / target stats** per loadout: pick a level dummy or customize armor and per-type resistances.
- A free-form **Custom Modifiers** editor — type one modifier per line, each line color-coded by whether it's recognized, with a hover tooltip.

### Calcs / Player Stats
- New boxes for **Numbed**, ailments, and crowd control; a **channeled** panel; and per-skill **Skill Effects** (projectile speed, penetration, jumps, and base mana cost).
- **Enemy Multiplier** and effective-resistance display, plus an enemy-type lever for enemy-count weighting.

### Quality of life
- **Global UI scale** slider and a **draggable sidebar** width.
- **Roll-tier badges** (T1/T2/…) on gear and hero-memory tooltips.
- **Share Feedback** button (Discord) on the main menu.
- Slate inventory: add-to-inventory and right-click remove/delete.

### Experimental (new — still being verified; please report any issues)
- **Loadouts** — multiple full-build variants inside one build, each able to inherit from a shared base, swappable from a sidebar dropdown.
- **Notes inline links** — type `@` in build notes to link an item, talent node, skill, hero trait, pact spirit, memory, or condition; shown as a colored chip with its tooltip on hover.
- **Pact Fates, Kismets, Dual Kismets, and Undetermined Fates** — install onto spirit nodes to replace their effects, with global limits and expansion slots.
- **Ethereal Prisms (24)** and the **Inverse Image** prism — craftable passive-tree items, including reflected-copy damage.
- **Hero traits:** Erika **Wind Stalker**, Rosa **Unsullied Blade** (spell-to-attack, Mercury Baptism), and Selena **Sing with the Tide** (Tide effects, Bard).

### Fixes
- Skill and support tooltips no longer wrongly mark modeled mechanics as "not implemented."
- Fixed craft base types failing to load.
- Removed the deprecated Debug Stats page.

---

## [0.5.2] - 2026-06-16

### Mana / Life sealing & reservation
- Auras, Focus, and Spirit Magus skills now **seal Mana / Life** when active. Full reservation math: base seal × support Mana Multipliers ÷ ((1 + Σ increased) × (1 + Σ additional)) Sealed Mana Compensation — with increased and additional tracked as separate multiplicative pools.
- **Seal Conversion** routes a seal onto Life (off Max Life) with its compensation penalty; **Off the Beaten Track** (95% support multiplier + support levels); **Ward** (Energy Shield from sealed pools); **Lunar Eclipse** (imparted seal + damage per Mana sealed).
- Player Stats shows **Sealed / Unsealed (Available) Life and Mana** with insufficient-pool warnings and clickable per-skill reservation breakdowns. Sealed + Unsealed always sum to Max and round against the player to match in-game; Energy Shield is truncated to match.
- Socketing rules: a base aura/support and its **Precise** variant are now mutually exclusive, and the same support can't be socketed twice on one skill.

### Auras & Focus as build buffs
- Equipped, enabled **Aura and Focus** skills now grant their buffs to the build, scaled by Aura Effect, flowing into the same stat pools offense and defense read. Per-aura buff breakdowns surface any not-yet-modeled lines.

### Updates & Settings
- **One-click silent updates** — no installer wizard, folder picker, or UAC prompt. After Download, "Restart & Install" relaunches straight onto the new version (a dirty build still prompts to save first).
- New **Settings overlay** (gear button in the sidebar and the build list) with a **Stable / Nightly** release-channel toggle, so you can opt into frequent nightly patches.
- Deleting a build now asks for confirmation first.

### Skills & supports
- Full **skill-data reimport** from the recrawl: deduplicated lines, detailed level-aware descriptions, and seal amounts.
- Rebuilt skill/support tooltips with structured, level-aware lines; a support **sort dropdown**; passive-skill DPS-delta sorting and a catalog **refresh button**.
- Supports and offense are computed **per skill slot** (no cross-slot contamination), with a Full-DPS sidebar and per-skill contribution toggles.
- Fixed Attack Focus phantom damage and mapped additional support lines.

### Talent tree, slates & stats
- **Bundled game icons** for talents, hero traits, pact spirits, and core talents; cross-tree **node search** on the overview.
- **Slate Board** rework: saved-slate inventory, floating tooltips, live editing, unified divinity-slate art, and affix tiers.
- **Stats screen v2**: three-column category layout, real source names, per-weapon sources, and crit shown as a tooltip.
- Character level is now driven by the level condition (default 90).

### Quality of life
- Custom title bar with logo and a dark window frame.
- Clearing a conditional's value resets it to its default; brighter, roomier talent tree.

---

## [0.5.1] - 2026-06-13

### Fixed
- Updating the app now refreshes the bundled game data. Previously an update kept the data copied at first install, so after updating the calculator could fail — skills showed no damage and every stat appeared inactive. Your saved builds are preserved.

---

## [0.5.0] - 2026-06-13

### Damage calculation
- Per-skill damage engine for **Berserking Blade, Focused Slash, Moon Strike, and Chain Lightning**, plus their **Magnificent/Noble (canvas) supports**. In-app badges mark every modifier as Consumed (working), Inactive (modeled, not for your skill), Unconsumed (not wired), or NYI, so anything not yet modeled is obvious at a glance.
- Verified against in-game dummy testing (2-minute Recount average), generally within ~3%; the remaining gap is mostly buff/debuff uptime, crit variance, and wide roll ranges.
- Mechanics modeled: Steep Strike / Sweep Slash, crit and crit damage, double/triple/quadruple damage, shotgun (Chain Lightning: Merge / Web), Chain Lightning: Augmentation, Lucky, Willpower, Fervor, main-stat damage bonus, and blessings (Focus/Agility/Tenacity).
- Damage-type conversion (e.g. Lightning to Cold); Elemental split into Fire/Cold/Lightning.
- Enemy mitigation: armor plus elemental/erosion resistance and all penetration types (can go negative to amplify), plus enemy debuffs (Numbed, Frail, Infiltration, Paralysis) shown in a target enemy-stats panel.
- Dual-wielding base effects.

### Skills and supports
- Enable/disable toggles on every active/passive skill and each individual support, saved with the build.
- Each support is calculated local to its skill slot, so separate setups don't cross-contaminate.
- Support Rank (1-5) and Tier controls, roll sliders, and explicit per-line rolls.

### Core talents and belt blends
- Core talents modeled and applied, shown on every tree with badges and a preview.
- Belt blend (Blending Ritual) selection via a searchable picker.

### Gear and crafting
- Gear modifiers are fully resolved and surfaced (nothing silently dropped), with engine badges shown in the affix and belt-blend pickers and the item preview before you add the item.
- Damage-delta previews on gear, multi-slot swaps, list reordering, and a live customization preview.
- Craft no-affix white items; suffix affix tiers; per-item Energy Shield / Armor / Evasion scaling.

### Stats, badges, and quality of life
- New interactive Player Stats screen with clickable source breakdowns.
- Derived stats (total Life, Energy Shield, Mana, and more) and a dedicated Energy Shield panel.
- Modifier badges app-wide with a clear four-state taxonomy (Consumed / Inactive / Unconsumed / NYI).
- DPS Delta previews on mods, nodes, and gear.
- Conditionals manager (low life, enemy debuffs, life %, proximity, and more), settable and auto-derived, with a tidier layout.
- Custom Mods panel; pact-spirit per-node and spirit-total DPS on hover; shared tooltips and broad UI revamps.

---

## [0.4.0] - 2026-05-28

### New Features
- **Calcs screen** — new Calcs tab in the sidebar with a full damage breakdown for the active skill in slot 1.
  - Per-hit-form display: effectiveness %, proc chance, average hit pre- and post-crit, DPS contribution per form.
  - Blended **Total DPS** and **vs Target Dummy** DPS (applies target dummy's baseline mitigation: 50% physical armor; 30% armor + 30% elemental/erosion resistance for non-physical damage).
  - Crit Chance, Crit Multiplier, Steep Strike Chance, and Attacks per Second displayed below the form breakdown.
  - NYI badge list shows which modifiers are not yet wired so numbers are always clearly partial rather than silently wrong.
  - Unsupported skills show a clear "not yet supported" state with no zeroed numbers.
- **Offense engine** — explicit per-skill damage pipeline. Only skills registered in the engine produce calculations; all others show NYI rather than a partial or guessed result.
  - **Berserking Blade** fully supported: Sweep Slash and Steep Strike as mutually exclusive hit forms; skill's intrinsic +20% Steep Strike chance passive parsed from skill data.
  - Above-max-level effectiveness scaling: ×1.10 per level for levels max+1 to max+10, ×1.08 per level beyond that (compound).
  - Tag-filtered increased damage pool: all `*_dmg_inc` stats from the talent tree whose tags intersect the skill's tag set are summed into a single additive multiplier. Generic (untagged) stats always apply.
  - Crit formula: final CSR ÷ 10000 = crit chance (100 CSR = 1%).
- **Legendary gear corruption** — Corruption dropdown (None / Desecration / Mutation) on legendary items that have a corroded variant.
  - **Desecration** — toggle up to 2 explicit modifiers to their corroded tier; affected rows highlight in purple and stats update immediately.
  - **Mutation** — select one slot-specific mutation implicit from the craft base pool; appears in purple above regular implicits and contributes to stats.
- **Legendary random affix pools** — placeholder "Random X" explicits now show an enabled dropdown listing all valid options. Selecting eagerly swaps the affix; range sliders appear for numeric affixes. Selection persists across save/load.
- **Craft item corruption** — Corruption dropdown (None / Desecration / Mutation) on crafted items.
  - **Desecration** — per-slot toggle (max 2) upgrades to T0+; T0+ is excluded from the dropdown unless the slot is already corroded.
  - **Mutation** — replaces both base slots from the corrosion pool with range sliders for numeric modifiers.
- **Dev data inspector** — browser tool at `/api/dev/inspect/` for exploring season JSON files: field discovery, variant exploration, filtered queries, syntax-highlighted output.

### Improvements
- **Weapon implicit stat parsing** — crafted weapon base types (Physical Damage, Attack Speed, Critical Strike Rating) now resolve to engine stat keys and feed the damage calculation correctly.
- **Dev-mode API gating** — `/api/dev/*` routes return 404 in packaged builds.
- **Legendary corrosion toggle redesigned** — inline 7×7 px square to the left of modifier text; active = solid purple, inactive = dim border.

### Bug Fixes
- Fixed tag-filtered increased damage from talent nodes not applying to skill damage — `inc_total` was a hardcoded 0.0 placeholder; now reads all matching `*_dmg_inc` stats from the talent tree filtered by skill tags.
- Fixed Berserking Blade showing 0% Steep Strike chance — the skill's intrinsic `+20% Steep Strike` passive was not being parsed from skill data.
- Fixed crafted weapon implicits (Physical Damage, Attack Speed, CSR) not contributing to engine stats — `affix_kind: 'implicit'` affixes have no resolved stat keys and were silently skipped by the payload builder.
- Fixed skills cache always empty — `_get_skills_data()` was reading the wrong root key (`"items"` instead of `"skills"`) from `_skills.json`, causing offense calculation to never run.
- Fixed crit chance always 100% for any weapon with CSR — the formula used `raw_csr / 100` instead of `/ 10000` (500 CSR should be 5%, not 500%).
- Fixed mutation affix pool not populating after reimporting craft base types — the reference store now refreshes immediately after a successful DevTools import.
- Fixed mutation affixes having no stat contribution — `corrosion_base` entries are now parsed with `parse_affix_text` at import time.
- Fixed craft modifier dropdown grouping fixed-value tiers separately from range-value tiers — tier groups are now keyed on a normalized expression with all numeric literals replaced by `#`.
- Fixed leaving Desecration mode clearing the selected modifier — slot now downgrades to the best non-corroded tier rather than clearing.
- Fixed blessing stack conditions having min_base and max_base swapped.

---

## [0.3.2] - 2026-05-25

### New Features
- **Conditions framework revamp** — condition system rebuilt on a fixed-point iteration engine. Numeric conditions (blessing/channeled stacks, enemy ailment/wilt/torment counts, trauma stacks) are now first-class with dynamic build-driven maximums. Boolean conditions support compound expressions (`and`/`or`/`not`/threshold operators). Per-stack scaling recipes can reference numeric condition values. Load-time validation rejects unknown or mistyped condition keys at startup rather than silently computing wrong values.
- **Data-driven Conditionals screen** — BuildOverviewScreen now renders entirely from the server's condition definitions. Numeric conditions show spinners with engine-derived maximums. Auto-derived active flags (`tenacity_active`, `agility_active`, `focus_active`) display as read-only indicators rather than user-toggleable checkboxes. Clamp warnings appear inline when a user's entered value exceeds the current build's dynamic maximum.

### Improvements
- **Unified `conditionState`** — replaces the previous split of `conditions: string[]` + `conditionValues: Record`. All condition values (boolean and numeric) now live in a single `conditionState` map on build, store, and API payload. Old builds are migrated automatically on load.
- **Build code migration** — `SCHEMA_VERSION` bumped to 2; old codes carrying `conditions`/`conditionValues` are migrated to `conditionState` transparently on import.

### Bug Fixes
- Fixed condition values not being preserved correctly across engine passes when a talent-derived maximum was lower than the user's entered stack count — the engine now clamps and reports clamped values rather than computing at the unclamped input.
- Fixed test fixture for `test_round_trip_rehydrates_legendary_gear` using a flat `affixes` shape instead of the real `variants` catalog format, which caused the round-trip test to fail on a correct rehydration path.
- **Support skill levels** — support skills now have level controls. Normal supports range from 1–40. Activation Medium, Magnificent, and Noble supports range from 0–2 (default 1). Old saves default to level 20 / `support_skill` type on load.
- **Support skill detail panel** — the description panel for a selected support now shows only the advanced/effect lines rather than the full raw description text.
- **Vorax gear slot enforcement** — Vorax items now auto-assign to their correct slot type on creation (e.g. Head limb → Helmet) and can only be dragged to valid slots, matching the behaviour of legendary and crafted items.
- **Slate board state preserved on navigation** — switching screens via the sidebar no longer discards uncommitted slate changes; state is now synced to session on every board mutation rather than only on "Done".
- **Moth/Prairie slate copy in stat calculations** — fixed two bugs: (1) the board position map was built with doubled anchor offsets because cells are stored as absolute board positions; (2) all slots were being copied instead of only the bottom slot, which is what the mechanic specifies.
- Fixed nine stale stat enum references in `node_modifier_pool.py` (`CRIT_DMG` → `CRIT_DMG_INC`, `PHYSICAL_` prefix additions) that prevented all backend tests from collecting.
- Fixed `coreTalentSelections` typed as `Record<number, string>` — JSON keys are always strings; changed to `Record<string, string>` and updated the `sanitizeSlot` migration guard accordingly.
- Fixed `'conditional'` missing from the `UnresolvedStat.reason` union type, causing a spurious TypeScript error in DevToolsScreen.
- Fixed "What's New" update dialog showing raw HTML tags — release notes are now rendered as HTML with styled headings, lists, and code spans.

---

## [0.3.1] - 2026-05-25

### Bug Fixes
- Fixed pact spirit outer/main skill being counted twice in stat calculations — outer effects now come from the selected rank's modifiers only, not the base slot effect.
- Fixed gear stats missing after importing a build via build code or share link — legendary items are now fully rehydrated with a flat affixes list on decode.
- Fixed notes, hero traits, hero memories, and pact spirits not being saved — extra fields were silently dropped by Pydantic v2; resolved with `extra='allow'` on `BuildRequest`.

### Security
- Path traversal guard on build IDs and season names in the Python backend.
- `shell.openExternal` restricted to `http://` and `https://` URLs only.
- Renderer sandbox enabled.
- Share service responses capped at 512 KB; `tli1_` prefix validated before decode.

### Other
- Windows Start Menu and taskbar now show the TLI Builder icon instead of the default Electron icon.

---

## [0.3.0] - 2026-05-24

### New Features
- **Share via Link** — export tab now includes a "Share via Link" button that uploads the build code to the share service and returns a short URL. Both import fields (overlay and build select screen) accept either a raw `tli1_` code or a share link.
- **Crafted/Vorax item re-edit** — previously crafted and Vorax items in the build can now be reopened and edited directly from the gear screen instead of having to re-craft from scratch.
- **Instant screen navigation** — all season-global catalogs (legendary gear, craft bases, grafts, hero traits, hero memories, conditions) are now prefetched once at app init. Returning to GearScreen, HeroTraitScreen, BuildOverviewScreen, and PactSpiritScreen is instant after the first load.

### Improvements
- **Dual-value and range-multi affix display** — gear affixes that represent two separate ranges (dual-stat) or split min/max values now display and compute correctly.
- **Hero memory stat coverage** — alias lookups and multi-stat mappings added for hero memory modifiers that previously returned no stat contribution.
- **Stat resolver extended** — ~60 new stat enum values added; crit damage keys renamed for consistency; new override entries and normalization fixes for edge-case modifier text.

### Bug Fixes
- Fixed gear stat resolution for crafted items loaded from a saved build (affix `stat_key` fields were not being rehydrated on build open).
- Fixed Content Security Policy blocking outbound requests to the share service (`https://api.tlibuilder.com` added to `connect-src`).

---

## [0.2.0] - 2025-12-01

- Hero Memories and Pact Spirits features
- Version display, Check for Update, and About buttons on main menu

## [0.1.1] - 2025-11-15

- Auto-updater, dev mode gating, and packaging config fixes

## [0.1.0] - 2025-11-10

- Initial release

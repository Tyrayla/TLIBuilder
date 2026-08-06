# TLI Builder

A build planner for Torchlight: Infinite - plan your talents, gear, and more.

## Download

Download the latest release from the [Releases page](https://github.com/Tyrayla/TLIBuilder/releases/latest).

## Installation

1. Download `TLI-Builder-Setup-x.x.x.exe` from the latest release
2. Run the installer
3. Launch **TLI Builder** from the desktop shortcut or Start Menu

## Development setup

The game dataset is not stored in this repository. After cloning, fetch it from the
private data source:

```
npm install
npm run fetch:data
```

`fetch:data` populates `data/` from the private `tli-data` repository. You need read
access to that repo (set `TLI_DATA_TOKEN` to a token, or be authenticated with git for
`github.com/Tyrayla/tli-data`). CI does this automatically with a repository secret.

## Licensing

The TLI Builder source code is licensed under the MIT License (see LICENSE).

The game data is separate and is not covered by that license. It is aggregated from the
game and community sources (mostly TLIDB, used with permission) and maintained for this
project each season. Please do not scrape, rehost, or embed the compiled data files that
TLI Builder serves in other sites or services. See DATA-LICENSE.md.

To ask about using the data, contact the author at Tyrayla@gmail.com, open an issue on
GitHub, or see about.tlibuilder.com.

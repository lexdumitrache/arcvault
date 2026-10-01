# Arc's on-disk data

Arc doesn't document its storage format. Everything below was checked against
**Arc 1.165.1 on macOS** (October 2026) by reading files read-only. Anything not
verified is marked as such. If your Arc version differs, run `arcvault inspect`.

Root: `~/Library/Application Support/Arc/`

| File | What it holds | ArcVault |
|---|---|---|
| `StorableSidebar.json` | Spaces, pinned and Today tabs, folders, favorites | ✅ `sources/sidebar.py` |
| `StorableArchiveItems.json` | Archived tabs: auto-archived and manually closed | ✅ `sources/archive.py` |
| `StorableArchive.json` | 64-byte stub on this machine; no tab data seen | ignored |
| `Storable*.<timestamp>.json` | Arc's own rolling backups of the files above | ignored (older copies) |
| `User Data/<Profile>/History` | Chromium history SQLite | ✅ `sources/history.py` |
| `User Data/<Profile>/Sessions/Session_*`, `Tabs_*` | Chromium SNSS session files | ✅ `sources/sessions.py` |
| `ArchiveSnapshotCache/`, `*FaviconCache/` | Images | not used |

Profiles are named `Default`, `Profile 1`, `Profile 2`, and so on. Each Space points to one profile.

## Encoding conventions

**Swift dictionaries become flat alternating lists:** `[key, value, key, value, …]`.
Keys are plain strings, or single-key objects such as `{"pinned": {}}`. `arc/schema.py:pairs()` decodes them.

**Timestamps** (`createdAt`, `timeLastActiveAt`, `archivedAt`) are Foundation
seconds since **2001-01-01 UTC**. Chromium timestamps (History) are
**microseconds since 1601-01-01 UTC**.

## StorableSidebar.json

Two copies of the item graph exist:

```text
sidebar.containers[1]            # local copy: {items, spaces, topAppsContainerIDs}
sidebarSyncState                 # sync copy: items/spaceModels wrapped as {value, encodedCKRecordFields}
  .container.value.orderedSpaceIDs
```

ArcVault prefers the local copy and falls back to the sync copy. On the test
machine both held identical item sets.

### Items

Every item has this shape:

```json
{"id": "UUID", "parentID": "UUID|null", "childrenIds": ["UUID", ...], "title": "str|null",
 "createdAt": 780000000.0, "data": {"<kind>": {...}}}
```

| `data` kind | Meaning | Fields seen |
|---|---|---|
| `tab` | A tab | `savedURL`, `savedTitle`, `timeLastActiveAt`, `savedMuteStatus`, `activeTabBeforeCreationID`?, `referrerID`?, `customInfo`? |
| `list` | A folder. Nests to any depth (3 levels seen) | none |
| `itemContainer` | A root | `containerType`: `{"spaceItems": {"_0": spaceID}}` or `{"topApps": {"_0": profile}}` |
| `splitView` | Tabs shown side by side | `layoutOrientation`, `focusItemID`, `itemWidthFactors` |

`item.title` on a tab holds the user's custom name for it. `savedTitle` holds the page title.

### Spaces

```json
{"id": "UUID", "title": "Work", "profile": {"default": true} | {"custom": {"_0": {"directoryBasename": "Profile 3"}}},
 "containerIDs": ["unpinned", ID, "pinned", ID],
 "newContainerIDs": [{"unpinned": {...}}, ID, {"pinned": {}}, ID]}
```

The `pinned` container holds the Space's saved tabs and folders. The `unpinned`
container holds the "Today" tabs, which auto-archive.

### Favorites

`topAppsContainerIDs` is `[profileKey, containerID, …]` with one favorites
container per profile. ArcVault assigns each one to the first Space that uses
that profile.

## StorableArchiveItems.json

```json
{"version": 1, "items": [id, {"sidebarItem": <tab item>, "source": {"space": {"_0": spaceID}} | {"littleArc": {}} | {"unknown": {}},
                              "reason": "manual" | "auto", "archivedAt": 780000500.0}, ...]}
```

All three `source` kinds and both `reason` values were seen on the test
machine.

## History

Standard Chromium schema. ArcVault reads `urls(url, title, visit_count, last_visit_time, hidden)`,
skips rows with `hidden = 1`, and skips `chrome://`, `arc://`, `about:`, `data:`
and `file://` URLs. The database is copied to a temp directory first, so the
live file is never opened.

## Sessions (SNSS)

`"SNSS"`, then an int32 version (3 here), then records of the form
`[uint16 size][uint8 command id][payload]`. Navigation payloads are
`base::Pickle` objects containing a tab id, an index, a URL (UTF-8) and a title
(UTF-16LE).

Command ids vary by file type and Chromium version. ArcVault therefore does not
filter on ids: it tries every payload and keeps the ones that decode to an
`http(s)` URL. On the test machine this recovered several hundred URLs.

## Not yet verified

- Arc on Windows (different root path and possibly different files)
- `easel`/`note` node types (listed as known but never seen; their children are still walked)
- Any other sidebar layout. Unknown node types are counted, reported in
  `--verbose`, and their children are still extracted.

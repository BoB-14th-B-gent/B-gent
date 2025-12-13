# Browser-DB-Parser MCP Strategy

## Purpose
Parse pre-extracted browser SQLite database files (Chrome History, Firefox places.sqlite, Edge History).

## CRITICAL LIMITATION
**This server CANNOT read E01 disk images directly!**
- Only works with pre-extracted SQLite files
- For E01 browser analysis, use **dissect** server with browser.history plugin instead

## Available Tools (2 tools only)

### 1. parse_history
- Parse browser history from SQLite file
- Required params: `history_file_path` (path to .sqlite file)
- Supported files:
  - Chrome: `History` (SQLite)
  - Firefox: `places.sqlite`
  - Edge: `History` (SQLite)

### 2. get_info
- Get information about browser database structure

## When to Use This Server
- ONLY when you have pre-extracted browser SQLite files
- Files must already exist on the filesystem
- Example valid paths: `/tmp/extracted/History`, `/data/places.sqlite`

## When NOT to Use This Server
- When analyzing E01/dd/raw disk images → Use **dissect** instead
- When browser databases have not been extracted yet

## Common Mistakes to Avoid
- Do NOT try to use E01 image path with parse_history - it will fail
- Do NOT assume /tmp/browser_dbs/ contains files - verify extraction first
- Do NOT use wildcard patterns (*.sqlite) - specify exact file path

## Parameter Examples
```json
// Parse extracted Chrome history
{"history_file_path": "/tmp/extracted/Chrome/History"}

// Parse extracted Firefox history
{"history_file_path": "/tmp/extracted/Firefox/places.sqlite"}
```

## Alternative for E01 Images
If you need to analyze browser history from E01 disk images:
1. Use **dissect** server
2. Call `list_artifact_plugins` to see available plugins
3. Call `run_artifact_plugin` with `plugin_name: "browser"` or `"browser.history"`

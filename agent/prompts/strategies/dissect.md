# Dissect MCP Strategy

## Purpose
Multi-purpose disk image analysis for .E01/.dd/.raw images. Supports Windows artifact collection including browser history, prefetch, amcache, registry, and more.

## Available Plugins (from list_artifact_plugins)

### Stage 1에서 Dissect가 담당하는 아티팩트
| Key | Plugin | Description |
|-----|--------|-------------|
| evtx | os.windows.log.evtx.evtx | Windows Event Logs |
| prefetch | os.windows.prefetch | Prefetch files for program execution |
| jumplist | os.windows.jumplist | JumpList recent files |
| browser | browser.history | Chrome/Firefox/Edge/Brave/IE browser history |
| regf | os.windows.regf.regf | Full Registry |
| webserver | webserver.logs | Web server logs |
| nethist | os.windows.regf.nethist | Network History (네트워크 연결 기록) |
| mru.mstsc | os.windows.regf.mru.mstsc | Remote Desktop MRU |
| mru.opensave | os.windows.regf.mru.opensave | OpenSave MRU |

### Velociraptor가 담당하는 아티팩트 (Stage 1에서 Dissect 사용 안함)
| Key | Plugin | Description |
|-----|--------|-------------|
| amcache | os.windows.amcache | Amcache (Velociraptor 담당) |
| userassist | os.windows.regf.userassist | UserAssist (Velociraptor 담당) |
| shimcache | os.windows.regf.shimcache | Shimcache (Velociraptor 담당) |
| shellbags | os.windows.regf.shellbags | Shellbags (Velociraptor 담당) |
| bam | os.windows.regf.bam | BAM (Velociraptor 담당) |
| tasks | os.windows.tasks | Scheduled tasks (Velociraptor 담당) |
| mru.recentdocs | os.windows.regf.mru.recentdocs | RecentDocs (Velociraptor 담당) |

## Required Tool Sequence

### For Browser History Analysis from E01:
1. **list_artifact_plugins** - List available plugins
   - Required params: `image_path`

2. **run_single_plugin** - Run browser.history plugin
   - Required params: `image_path`, `plugin`, `max_rows`
   - Use: `plugin: "browser"` (use key, not full plugin name)

### For General Artifact Collection:
1. **list_artifact_plugins** - See available plugins first
2. **run_single_plugin** - Run specific plugin with correct key

## Parameter Examples
```json
// Step 1: List artifact plugins (no parameters needed)
// Returns: {"artifacts": [{"key": "browser", "plugin": "browser.history", ...}, ...]}

// Step 2: Run browser history plugin - use FULL plugin name, not key
{"image_path": "/path/to/Image.E01", "plugin": "browser.history", "max_rows": 1000}

// Run prefetch plugin
{"image_path": "/path/to/Image.E01", "plugin": "os.windows.prefetch", "max_rows": 1000}

// Run amcache plugin
{"image_path": "/path/to/Image.E01", "plugin": "os.windows.amcache", "max_rows": 1000}

// Run event logs plugin
{"image_path": "/path/to/Image.E01", "plugin": "os.windows.log.evtx.evtx", "max_rows": 500}

// Run shellbags plugin
{"image_path": "/path/to/Image.E01", "plugin": "os.windows.regf.shellbags", "max_rows": 1000}
```

## Common Mistakes to Avoid
- Do NOT use `run_artifact_plugin` - the correct tool is `run_single_plugin`
- Do NOT use `plugin_name` parameter - the correct parameter is `plugin`
- Do NOT use key value (e.g., "browser") - use FULL plugin name (e.g., "browser.history")
- Do NOT skip `max_rows` parameter - large artifacts like evtx/regf may timeout without limit
- Do NOT skip list_artifact_plugins - you need exact plugin names
- Do NOT call browser-db-parser for E01 browser analysis - use dissect instead

## Browser History Analysis Workflow
1. Call `list_artifact_plugins` (no parameters)
2. Find "browser" in results → note the `plugin` field: `"browser.history"`
3. Call `run_single_plugin` with `image_path`, `plugin: "browser.history"`, `max_rows: 1000`
4. Analyze the returned browser history records

## Filesystem Exploration (if needed)
- **target_fs** - Browse filesystem: `{"image_path": "...", "path": "/"}`
- **target_extract** - Extract files: `{"image_path": "...", "path": "...", "output_dir": "..."}`

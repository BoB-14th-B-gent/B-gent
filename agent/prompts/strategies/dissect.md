# Dissect MCP Strategy

## Purpose
Multi-purpose disk image analysis for .E01/.dd/.raw images. Supports Windows artifact collection including browser history, prefetch, amcache, registry, and more.

## Available Plugins (from list_artifact_plugins)
| Key | Plugin | Description |
|-----|--------|-------------|
| browser | browser.history | Chrome/Firefox/Edge/Brave/IE browser history |
| prefetch | os.windows.prefetch | Prefetch files for program execution |
| amcache | os.windows.amcache | Amcache program execution history |
| jumplist | os.windows.jumplist | JumpList recent files |
| shellbags | os.windows.regf.shellbags | Registry shellbags |
| shimcache | os.windows.regf.shimcache | Application compatibility cache |
| userassist | os.windows.regf.userassist | UserAssist program execution |
| bam | os.windows.regf.bam | Background Activity Moderator |
| tasks | os.windows.tasks | Scheduled tasks |
| mru.recentdocs | os.windows.regf.mru.recentdocs | RecentDocs MRU |

## Required Tool Sequence

### For Browser History Analysis from E01:
1. **list_artifact_plugins** - List available plugins
   - Required params: `image_path`

2. **run_artifact_plugin** - Run browser.history plugin
   - Required params: `image_path`, `plugin_name`
   - Use: `plugin_name: "browser"` or `plugin_name: "browser.history"`

### For General Artifact Collection:
1. **list_artifact_plugins** - See available plugins first
2. **run_artifact_plugin** - Run specific plugin with correct key

## Parameter Examples
```json
// Step 1: List plugins
{"image_path": "/path/to/Image.E01"}

// Step 2: Run browser history plugin
{"image_path": "/path/to/Image.E01", "plugin_name": "browser"}

// Run prefetch plugin
{"image_path": "/path/to/Image.E01", "plugin_name": "prefetch"}

// Run amcache plugin
{"image_path": "/path/to/Image.E01", "plugin_name": "amcache"}
```

## Common Mistakes to Avoid
- Do NOT skip list_artifact_plugins - you need exact plugin names
- Do NOT guess plugin names - use the "key" value from list_artifact_plugins output
- Do NOT call browser-db-parser for E01 browser analysis - use dissect instead

## Browser History Analysis Workflow
1. Call `list_artifact_plugins` with `image_path`
2. Find "browser" or "browser.history" in the results
3. Call `run_artifact_plugin` with `image_path` and `plugin_name: "browser"`
4. Analyze the returned browser history records

## Filesystem Exploration (if needed)
- **target_fs** - Browse filesystem: `{"image_path": "...", "path": "/"}`
- **target_extract** - Extract files: `{"image_path": "...", "path": "...", "output_dir": "..."}`

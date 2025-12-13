# LNK-Parser MCP Strategy

## Purpose
Parse Windows shortcut (.lnk) files for file access history, target paths, and timestamps.

## Required Tool Sequence

### For E01 Disk Image Analysis:
1. **auto_extract_and_parse_lnk** - Automatic extraction and parsing
   - Required params: `image_path` (path to .E01 file)
   - Automatically finds and parses all LNK files
   - Returns target paths, timestamps, volume info

### For Pre-extracted LNK Files:
1. **parse_lnk_file** - Parse single LNK file
   - Required params: `file_path` (path to .lnk file)

## Common Mistakes to Avoid
- Do NOT try to extract LNK files manually - use auto_extract_and_parse_lnk
- Do NOT use dissect for LNK analysis - this specialized server is better
- Do NOT call parse_lnk_file with E01 path (it expects .lnk file)

## Parameter Examples
```json
// Automatic extraction from E01
{"image_path": "/path/to/Image.E01"}

// Parse pre-extracted LNK file
{"file_path": "/tmp/extracted/Recent/document.lnk"}
```

## Key Information Extracted
- Target file path (what the shortcut points to)
- Creation/modification/access timestamps
- Volume serial number
- Machine ID
- Drive type
- File size of target

## Expected Workflow
1. auto_extract_and_parse_lnk with E01 -> Get all LNK info
2. Analyze target paths for suspicious file access
3. Create timeline of file access activities

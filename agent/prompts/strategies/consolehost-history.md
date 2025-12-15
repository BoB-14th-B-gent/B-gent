# ConsoleHost-History MCP Strategy

## Purpose
PowerShell forensics from disk images. Extract and parse ConsoleHost_history.txt for PowerShell command history.

## Supported Formats
- .E01, .EX01, .S01 (EnCase)
- .dd, .raw (Raw)

## Available Tools

### 1. extract_consolehost_history
Extract and parse PowerShell command history from disk images.
- **Required params:** `image_path` (string) - path to disk image file
- Automatically finds ConsoleHost_history.txt for ALL users
- Parses commands in memory (no output directory needed)
- Returns: Commands with user info, line numbers, partition info

### 2. get_info
Get tool information and capabilities.
- No required params
- Returns: version, supported images, target file path

## Parameter Examples
```json
// Extract PowerShell history from E01
{"image_path": "/path/to/Image.E01"}

// Check tool capabilities
{}
```

## Common Mistakes to Avoid
- Do NOT add `output_dir` parameter - it is NOT needed (parses in memory)
- Do NOT use dissect for PowerShell history - this specialized server is optimized for it

## Expected Workflow
1. Call `extract_consolehost_history` with `image_path` parameter
2. Analyze returned PowerShell commands for suspicious activity
3. Look for indicators like:
   - Encoded commands (Base64)
   - Download operations (Invoke-WebRequest, curl)
   - Credential harvesting
   - Lateral movement commands

## Response Structure
```json
{
  "success": true,
  "image_path": "/path/to/Image.E01",
  "files_found": 2,
  "files_extracted": 2,
  "extracted_files": [
    {
      "username": "suspect",
      "source_path": "/Users/suspect/AppData/Roaming/Microsoft/Windows/PowerShell/PSReadLine/ConsoleHost_history.txt",
      "file_size": 1234,
      "partition": "NTFS",
      "encoding": "utf-8",
      "command_count": 50,
      "commands": [
        {"line_number": 1, "command": "Get-Process"},
        {"line_number": 2, "command": "Invoke-WebRequest ..."}
      ]
    }
  ]
}
```

## Key Information Extracted
- Executed PowerShell commands with line numbers
- User account associated with commands
- Partition and encoding information
- Potentially malicious commands

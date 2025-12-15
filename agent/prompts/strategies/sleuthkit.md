# SleuthKit MCP Strategy

## Purpose
File extraction from disk images (.E01, .dd, .raw). Use for extracting specific files by path or inode.

## Required Tool Sequence

### Standard File Extraction:
1. **disk_info** - Get disk image information (partitions, filesystem)
   - Required params: `image_path`
   - Returns partition layout and filesystem info

2. **list_files** - List files in a directory
   - Required params: `image_path`, `path` (directory path like "/")
   - Optional: `partition_offset`

3. **extract_file** - Extract specific file
   - Required params: `image_path`, `file_path`, `output_path`
   - Optional: `partition_offset`, `inode`

### Quick Extraction (if path is known):
1. **extract_file** - Direct extraction
   - Required params: `image_path`, `file_path`, `output_path`

## Common Mistakes to Avoid
- Do NOT forget partition_offset for multi-partition images
- Do NOT use Windows paths (C:\) - use Unix paths (/Users/...)
- Do NOT omit output_path - specify where to save extracted file

## Parameter Examples
```json
// Get disk info first
{"image_path": "/path/to/Image.E01"}

// List root directory
{"image_path": "/path/to/Image.E01", "path": "/", "partition_offset": 0}

// Extract specific file
{
  "image_path": "/path/to/Image.E01",
  "file_path": "/Users/suspect/Downloads/malware.exe",
  "output_path": "/tmp/extracted/malware.exe"
}
```

## Expected Workflow
1. disk_info -> Identify partitions
2. list_files -> Navigate to target directory
3. extract_file -> Extract the target file

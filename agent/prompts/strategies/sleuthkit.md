# SleuthKit Disk Image Analysis Strategy

**Tool**: sleuthkit
**Purpose**: Disk image analysis and file extraction
**Common Use Cases**: Extract files from disk images, analyze filesystem structure

---

## Common Tool Usage Patterns

### 1. File Extraction by PATH (recommended for known file paths)

**Use**: sleuthkit.extract_files_by_path
**When**: You know the exact path of the file you want to extract

```json
{{"tool": "sleuthkit", "operation": "extract_files_by_path", "params": {{"image_path": "/full/path", "fs_offset_sectors": "2048", "paths": ["C:/Users/file.txt"]}}}}
```

**Parameters**:
- `image_path`: Full path to the disk image (e.g., "/data/disk.E01")
- `fs_offset_sectors`: Filesystem offset in sectors (get from partition info)
- `paths`: Array of file paths to extract (e.g., ["C:/Windows/System32/notepad.exe"])

### 2. File Extraction by INODE (only if you have inode numbers)

**Use**: sleuthkit.extract_files_by_inode
**When**: You have inode numbers from list_files

```json
{{"tool": "sleuthkit", "operation": "extract_files_by_inode", "params": {{"image_path": "/full/path", "fs_offset_sectors": "2048", "inodes": [12345, 67890]}}}}
```

**Parameters**:
- `image_path`: Full path to the disk image
- `fs_offset_sectors`: Filesystem offset in sectors
- `inodes`: Array of inode numbers to extract

### 3. List Files (to find files)

**Use**: sleuthkit.list_files
**When**: You need to browse the filesystem or find files

```json
{{"tool": "sleuthkit", "operation": "list_files", "params": {{"image_path": "/full/path", "fs_offset_sectors": "2048", "directory": "/path"}}}}
```

**Parameters**:
- `image_path`: Full path to the disk image
- `fs_offset_sectors`: Filesystem offset in sectors
- `directory`: Directory to list (e.g., "/Users" or "C:/Windows")

---

## Recommended Workflow

### Step 1: Get Partition Information

**First**, get disk partition info to find fs_offset_sectors:
```json
{{"tool": "sleuthkit", "operation": "list_partitions", "params": {{"image_path": "/data/disk.E01"}}}}
```

This returns partition layout with offset information.

### Step 2: List Files or Extract Files

**Then**, use the fs_offset_sectors from Step 1:
```json
{{"tool": "sleuthkit", "operation": "list_files", "params": {{"image_path": "/data/disk.E01", "fs_offset_sectors": "2048", "directory": "/"}}}}
```

### Step 3: Extract Target Files

**Finally**, extract the files you need:
```json
{{"tool": "sleuthkit", "operation": "extract_files_by_path", "params": {{"image_path": "/data/disk.E01", "fs_offset_sectors": "2048", "paths": ["C:/Users/victim/Desktop/malware.exe"]}}}}
```

---

## Best Practices

1. **Always get partition info first** - You need fs_offset_sectors for file operations
2. **Prefer extract_files_by_path over extract_files_by_inode** - Paths are easier to work with
3. **Use full absolute paths** - Both for image_path and file paths
4. **Check filesystem type** - NTFS uses different path format than ext4

---

## Common Mistakes to AVOID

- Skipping list_partitions and guessing fs_offset_sectors
- Using relative paths instead of absolute paths
- Not providing fs_offset_sectors parameter
- Using wrong path format (Windows vs Linux style)

---

**Last Updated**: 2025-11-24

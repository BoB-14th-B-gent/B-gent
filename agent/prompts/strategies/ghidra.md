# Ghidra MCP Strategy

## Purpose
Binary/malware analysis using Ghidra for reverse engineering, disassembly, and decompilation.

## Required Tool Sequence

### Standard Analysis:
1. **import_binary** - Import binary file for analysis
   - Required params: `binary_path` (path to PE/ELF file)
   - Creates a Ghidra project and imports the binary
   - Returns project info and initial analysis

2. **analyze_binary** - Run Ghidra analyzers
   - Required params: `project_name` (from import_binary)
   - Runs auto-analysis (function detection, string analysis, etc.)

3. **get_functions** - List detected functions
   - Required params: `project_name`
   - Returns function names, addresses, sizes

4. **decompile_function** - Decompile specific function
   - Required params: `project_name`, `function_name` or `address`
   - Returns C-like pseudocode

5. **get_strings** - Extract strings from binary
   - Required params: `project_name`
   - Returns embedded strings (useful for IoC extraction)

## Common Mistakes to Avoid
- Do NOT skip import_binary - must import before any analysis
- Do NOT forget to analyze_binary before decompiling
- Do NOT use wrong project_name in subsequent calls
- Do NOT decompile without knowing function names/addresses

## Parameter Examples
```json
// Step 1: Import binary
{"binary_path": "/tmp/extracted/malware.exe"}

// Step 2: Analyze (use project_name from step 1)
{"project_name": "malware_exe_12345"}

// Step 3: Get functions
{"project_name": "malware_exe_12345"}

// Step 4: Decompile interesting function
{"project_name": "malware_exe_12345", "function_name": "main"}

// Step 5: Get strings
{"project_name": "malware_exe_12345"}
```

## Key Analysis Points
- Entry point and main function behavior
- Suspicious API calls (CreateRemoteThread, VirtualAlloc, etc.)
- Embedded strings (URLs, IPs, registry keys)
- Crypto constants (AES S-box, RC4 constants)
- Anti-analysis techniques

## Expected Workflow
1. import_binary -> Get project_name
2. analyze_binary -> Run auto-analysis
3. get_strings -> Quick IoC extraction
4. get_functions -> Identify interesting functions
5. decompile_function -> Deep analysis of suspicious functions

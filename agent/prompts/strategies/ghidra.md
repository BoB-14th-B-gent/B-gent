# Ghidra Binary Analysis Strategy

**Tool**: ghidra
**Purpose**: Binary reverse engineering and decompilation
**Critical**: NEVER import a binary more than once

---

## Best Practice - Binary Analysis Workflow

When analyzing a binary (CTF challenge, malware, or unknown executable), follow these steps systematically:

### Phase 1 - Metadata Collection

1. Import binary (ghidra.import_binary)
2. Extract binary name from response
3. Get program information (architecture, entry point, segments)
4. Get strings (look for hints, flags, interesting strings)
5. List imports/exports (identify library functions used)
6. List all functions (get overview of program structure)

### Phase 2 - Initial Analysis

1. Decompile entry function (understand program initialization)
2. Decompile main function (understand core logic)
3. Identify key functions based on:
   - String references (e.g., functions that print "Correct!" or "Wrong!")
   - Import usage (e.g., functions calling scanf, strcmp, etc.)
   - Function names (e.g., check_password, validate_input)

### Phase 3 - Detailed Analysis

1. Decompile key functions identified in Phase 2
2. Analyze validation logic, encryption/decoding algorithms
3. Trace call chains (from entry → main → validation functions)
4. Look for vulnerabilities (buffer overflow, format string, etc.)

### Phase 4 - Synthesis

1. Combine findings from all phases
2. Identify the solution (flag, password, exploit method)
3. Provide comprehensive analysis report

---

## CRITICAL WARNINGS - READ BEFORE USING GHIDRA

- **NEVER call import_binary more than ONCE** - if you already called it, NEVER call it again even if functions are empty!
- **NEVER call list_project_binaries after import_binary** - the binary name is ALREADY in the import_binary observation!
- **NEVER use placeholders** like "binary.exe-<suffix>" or "binary.exe-abc123" - use the EXACT name from observation!
- **NEVER call non-existent tools** like "list_all_functions", "list_segments", "analyze_program_structure", "list_project_program_info"
- **NEVER call search_functions_by_name with empty query** - always provide a search pattern!
- If functions list is empty or "main" not found, try "entry" or "FUN_" instead - DO NOT re-import!
- **ONLY use these Ghidra tools**: import_binary, search_strings, list_imports, list_exports, search_functions_by_name, decompile_function, list_cross_references

---

## Tool Execution Workflow

### STEP 1: Import binary into Ghidra project

**Use ghidra.import_binary FIRST (and ONLY ONCE!)**
```json
{{"tool": "ghidra", "operation": "import_binary", "params": {{"binary_path": "/full/path/to/binary.exe"}}}}
```

- This will automatically wait for analysis to complete (may take 30-60 seconds)
- Response will include: "Analysis completed. Binary name: file.exe-abc123"
- The binary name is at the END of the response after "Binary name: "
- DO NOT call list_project_binaries - the binary name is ALREADY provided!

### STEP 2: Extract the binary name DIRECTLY from iteration 1's observation

**CRITICAL: The import_binary observation ALREADY contains the binary name!**
- Look for "Binary name: " in the iteration 1 observation
- Example: "...Analysis completed. Binary name: chall1.exe-e3d058"
- Extract: "chall1.exe-e3d058" (the text after "Binary name: ")
- DO NOT call list_project_binaries to get the binary name - it's already there!
- The binary name has a RANDOM SUFFIX (e.g., "file.exe-e3d058" NOT "file.exe")
- NEVER invent or guess the suffix - ALWAYS extract it from iteration 1's observation

### STEP 3: Use the exact binary name in ALL subsequent ghidra calls

**For all operations, use binary_name parameter:**
- decompile_function: {{"binary_name": "binary.exe-abc123", "name": "main"}}
- search_functions_by_name: {{"binary_name": "binary.exe-abc123", "query": "main", "limit": 20}}
- list_exports: {{"binary_name": "binary.exe-abc123", "query": ".*", "limit": 100}}
- list_imports: {{"binary_name": "binary.exe-abc123", "query": ".*", "limit": 100}}
- search_strings: {{"binary_name": "binary.exe-abc123", "query": ".*", "limit": 100}}

---

## Ghidra Tool Usage Guide

### search_strings
**Purpose**: Search for strings in binary (useful for finding hints, flags, error messages)
- Call this EARLY in analysis (right after import_binary)
- Parameters: binary_name, query (regex pattern), limit
- Example: {{"binary_name": "file.exe-abc123", "query": "flag|password|correct", "limit": 50}}

### list_imports
**Purpose**: Get imported functions (understand what libraries the program uses)
- Call this in Phase 1 (metadata collection)
- Parameters: binary_name, query (optional regex), offset, limit
- Example: {{"binary_name": "file.exe-abc123", "query": ".*", "limit": 100}}

### list_exports
**Purpose**: Get exported functions (useful for DLLs or libraries)
- Parameters: binary_name, query (optional regex), offset, limit
- Less common for executables, but useful for analyzing DLLs

### search_functions_by_name
**Purpose**: Search for functions by name pattern
- Parameters: binary_name, query (substring search), offset, limit
- Example: {{"binary_name": "file.exe-abc123", "query": "main", "limit": 20}}
- Useful for finding validation or crypto functions

### decompile_function
**Purpose**: Get C-like pseudocode for a function
- Parameters: binary_name, name (function name)
- Start with "entry", "main", then move to specific functions
- Expensive operation - be selective about which functions to decompile

### list_cross_references
**Purpose**: Find all references to a function/symbol
- Parameters: binary_name, name_or_address
- Useful for understanding call chains
- Example: see what functions call main()

---

## Optimal Analysis Sequence

### Phase 1 - Metadata Collection (DO FIRST)

1. import_binary (wait for completion automatically) - **ONLY ONCE!**
2. search_strings with query=".*" or specific patterns
3. list_imports with query=".*"
4. list_exports with query=".*" (if relevant)
5. **FINISH metadata collection** - even if you can't find functions, metadata alone is valuable

### Phase 2 - Function Analysis (DO AFTER metadata, SKIP if functions empty)

6. search_functions_by_name with query="entry" (try "entry" first, not "main")
7. If "entry" found, decompile_function with name="entry"
8. If "entry" not found, try query="FUN_" to find Ghidra default function names
9. If still empty, **SKIP this phase** - DO NOT try to re-import or keep searching

### Phase 3 - Analysis Completion

10. If you have strings and imports, that's enough for basic analysis
11. Provide summary of findings (strings like "Correct"/"Wrong", imports, etc.)
12. Set finished=true - **DO NOT keep retrying if functions are empty**

**CRITICAL**: In metadata collection tasks, DO NOT use list_cross_references. Only use it AFTER you have successfully identified specific function names.

---

## Common Mistakes to AVOID

- Calling import_binary multiple times (NEVER re-import even if functions are empty!)
- Using original binary name instead of the suffixed name (e.g., "file.exe" instead of "file.exe-e3d058")
- Using placeholder binary names like "file.exe-<suffix>" or inventing suffixes
- Using wrong suffix (e.g., "file.exe-bdcb65b4" when observation shows "file.exe-e3d058")
- Calling non-existent tools like "list_all_functions", "list_segments"
- Calling search_functions_by_name with empty query="" (always provide a pattern!)
- Re-importing when functions are empty (causes timeout, doesn't fix the problem)
- Trying to decompile "main" when it doesn't exist (try "entry" instead)
- Not extracting the binary name from import_binary observation
- Decompiling ALL functions (too slow, focus on key functions)
- Skipping string analysis (strings often contain critical hints)
- Giving up if functions are empty (strings and imports are still valuable!)

---

## Example Workflows

### Successful Analysis (with functions)

```
Iteration 1: ghidra.import_binary
  → "Binary name: chall1.exe-e3d058"

Iteration 2: ghidra.search_strings
  Params: {{"binary_name": "chall1.exe-e3d058", "query": ".*", "limit": 100}}

Iteration 3: ghidra.list_imports
  Params: {{"binary_name": "chall1.exe-e3d058", "query": ".*", "limit": 100}}

Iteration 4: ghidra.search_functions_by_name
  Params: {{"binary_name": "chall1.exe-e3d058", "query": "entry", "limit": 20}}

Iteration 5: ghidra.decompile_function
  Params: {{"binary_name": "chall1.exe-e3d058", "name": "entry"}}

Iteration 6: Set finished=true with comprehensive analysis
```

### Fallback Analysis (functions empty - THIS HAPPENS SOMETIMES!)

```
Iteration 1: ghidra.import_binary
  → "Binary name: chall1.exe-e3d058"

Iteration 2: ghidra.search_strings
  → Found "Correct", "Wrong", "Input : "

Iteration 3: ghidra.list_imports
  → Found scanf, printf, strcmp imports

Iteration 4: ghidra.search_functions_by_name(query="entry")
  → Empty array

Iteration 5: ghidra.search_functions_by_name(query="FUN_")
  → Empty array

Iteration 6: Set finished=true with analysis based on strings and imports only
  Answer: "Based on strings ('Correct', 'Wrong') and imports (scanf, strcmp),
           this appears to be a password validation program. Functions list
           is empty due to Ghidra analysis limitation, but strings provide
           sufficient insight into program behavior."
```

---

## CRITICAL RULES

1. After import_binary (iteration 1), you ALREADY have the binary name
2. DO NOT call list_project_binaries in iteration 2 or later
3. DO NOT re-import if functions are empty - provide analysis from metadata
4. Use the SAME binary_name in ALL iterations after import
5. If functions empty, finish with strings/imports analysis - DO NOT retry endlessly!

---

**IMPORTANT - If search_functions_by_name returns empty:**
- DO NOT call import_binary again!
- Try searching for "entry" function instead of "main"
- Try searching for "FUN_" (Ghidra's default function naming)
- If still empty, provide analysis based on strings and imports only
- NEVER re-import the binary - it won't fix the problem and causes timeout!

---

**Last Updated**: 2025-11-24
**Related**: agent/prompts/react_think_system.txt

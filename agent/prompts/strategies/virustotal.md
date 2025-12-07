# VirusTotal Threat Intelligence Strategy

**Tool**: virustotal
**Purpose**: Malware reputation lookup and threat intelligence
**Recommendation**: Always use *_report tools first

---

## CRITICAL RULE - ALWAYS USE *_report TOOLS FIRST AND PRIMARILY

- [OK] **ALWAYS use** get_file_report, get_url_report, get_ip_report, or get_domain_report
- [OK] These *_report tools provide **COMPLETE and COMPREHENSIVE** data
- [X] **DO NOT use** *_relationship tools (get_file_relationship, get_url_relationship, etc.) unless the user EXPLICITLY asks for relationships/related items
- [X] The *_relationship tools often fail and provide incomplete data compared to *_report tools

---

## Available Report Tools

### 1. File Analysis (virustotal.get_file_report)

**Purpose**: Get complete file analysis and reputation

```json
{{"tool": "virustotal", "operation": "get_file_report", "params": {{"hash": "sha256_or_md5_or_sha1"}}}}
```

**Returns COMPLETE analysis including:**
- File metadata (name, type, size, hashes)
- Detection results from 70+ antivirus engines
- File signatures and behavior analysis
- Community votes and reputation
- Behavioral information

**[OK] This SINGLE call is sufficient for file analysis** - DO NOT call relationship tools afterward

### 2. URL Analysis (virustotal.get_url_report)

**Purpose**: Get comprehensive URL scan results

```json
{{"tool": "virustotal", "operation": "get_url_report", "params": {{"url": "http://example.com"}}}}
```

Returns comprehensive URL scan results from multiple engines.

### 3. IP Analysis (virustotal.get_ip_report)

**Purpose**: Get complete IP reputation and analysis data

```json
{{"tool": "virustotal", "operation": "get_ip_report", "params": {{"ip": "1.2.3.4"}}}}
```

Returns complete IP reputation and analysis data.

### 4. Domain Analysis (virustotal.get_domain_report)

**Purpose**: Get comprehensive domain reputation and analysis

```json
{{"tool": "virustotal", "operation": "get_domain_report", "params": {{"domain": "example.com"}}}}
```

Returns comprehensive domain reputation and analysis.

---

## Recommended Workflow

### Standard Analysis Workflow

1. **Call the appropriate *_report tool once** (get_file_report, get_url_report, etc.)
2. **Analyze the comprehensive data returned**
3. **FINISH with your analysis** - DO NOT call *_relationship tools
4. **Only if user explicitly asks** "show me related files/URLs/IPs" → then use *_relationship tools

---

## Best Practices

### [OK] DO

- [OK] **ALWAYS prefer *_report over *_relationship**
- [OK] **ONE *_report call is sufficient** - analyze it thoroughly
- [OK] Use get_file_report for any hash (MD5, SHA1, SHA256)
- [OK] Finish immediately after getting report data

### [X] DON'T

- [X] **NEVER call *_relationship tools unless explicitly requested**
- [X] **NEVER repeat the same *_report call multiple times**
- [X] Don't call relationship tools "just to be thorough"
- [X] Don't keep calling tools after getting complete data

---

## CRITICAL - When you receive a LIST of items

**Example**: get_file_relationship returns list of 8 dropped files

**If one item from the list fails (e.g., "file not found"):**

1. **DO NOT retry the same item**
2. **Move to the NEXT item in the list** and try that instead
3. Continue trying different items from the list until you find one that succeeds
4. If you've tried several items and all fail, then finish with what you have
5. **NEVER retry the same failed item** from a list - always move forward to the next one

### Example Workflow

```
Iteration 1: get_file_relationship
  → Returns list of 8 dropped files

Iteration 2: get_file_report on file #1
  → Fails "not found"

Iteration 3: get_file_report on file #2
  → Try the second file (DON'T retry file #1!)

Iteration 4: get_file_report on file #3
  → If #2 failed, try third file

Iteration 5: If #3 succeeds, analyze and finish
  → Don't keep trying all 8 files
```

---

## When to Finish

**[OK] FINISH immediately when:**
- VirusTotal get_file_report returned data → FINISH with analysis
- You have enough information to answer the user's question
- The last observation contains complete results
- One successful report from a list of items

**[X] DON'T:**
- Keep calling tools "just to be thorough"
- Try all items in a list if you already have one success
- Call relationship tools after getting report data

---

## Common Mistakes to AVOID

- Using get_file_relationship when user asks for file analysis (use get_file_report!)
- Calling relationship tools without explicit user request
- Retrying the same failed hash/URL/IP repeatedly
- Not finishing after getting complete report data
- Trying all items in a list instead of stopping after first success

---

**Last Updated**: 2025-11-24

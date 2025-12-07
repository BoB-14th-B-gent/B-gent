# Elasticsearch SIEM Analysis Strategy

**Tool**: elastic
**Purpose**: SIEM log analysis and security event queries
**Mode**: Read-only (no write operations allowed)

---

## ⚠️ CRITICAL WARNING - READ THIS FIRST ⚠️

**YOU MUST COMPLETE BOTH STEPS - DO NOT STOP AFTER STEP 1!**

**Common mistake that just happened:**
1. You call `list_indices` ✅
2. You see the indices exist ✅
3. You think "task done" and set `finished=true` ❌ **WRONG!**

**What you MUST do:**
1. Call `list_indices` (to see what indices exist)
2. **IMMEDIATELY call `search_documents`** (to ACTUALLY get data)
3. Analyze the data
4. THEN finish

**If you only called `list_indices`, YOU HAVE DONE NOTHING USEFUL!**
- list_indices = seeing a library catalog
- search_documents = actually reading books
- **You need BOTH!**

**NEVER set `finished=true` until you have called `search_documents` at least once!**

---

## AVAILABLE TOOLS (ONLY USE THESE!)

**YOU HAVE ACCESS TO EXACTLY 3 TOOLS:**
1. `list_indices` - List all available indices
2. `search_documents` - Search for documents in an index
3. `get_index_mapping` - Get field mappings for an index

**TOOLS THAT DO NOT EXIST (NEVER USE):**
- `general_api_request` - NOT AVAILABLE
- `get_data_streams` - NOT AVAILABLE
- `count_documents` - NOT AVAILABLE (removed from MCP server)
- `create_*`, `update_*`, `delete_*` - NOT AVAILABLE (read-only mode)

If you try to use a tool that doesn't exist, you will receive an "Unknown tool" error!

---

## MANDATORY WORKFLOW (BOTH STEPS REQUIRED!)

**THIS IS A 2-STEP PROCESS - YOU MUST DO BOTH STEPS!**

**STEP 1: Start with list_indices (FIRST ACTION)**
```json
{{"tool": "elastic", "operation": "list_indices", "params": {{}}}}
```
- Purpose: See what indices exist in the SIEM system
- Result: You get a list of index names (firewall-logs, sysmon-logs, etc.)
- ⚠️ **IMPORTANT: This is ONLY THE FIRST STEP! DO NOT STOP HERE!**
- ⚠️ **After this step, you have NO DATA yet - only index names!**

**STEP 2: IMMEDIATELY call search_documents (REQUIRED - DON'T SKIP!)**
```json
{{"tool": "elastic", "operation": "search_documents", "params": {{"index": "sysmon-logs", "body": {{"query": {{"match_all": {{}}}}, "size": 20}}}}}}
```
- Purpose: ACTUALLY retrieve and analyze log data
- Result: You get actual log entries to analyze
- ⚠️ **YOU MUST DO THIS! list_indices alone accomplishes NOTHING!**
- ⚠️ **If you don't call search_documents, you have NO data to analyze!**

**COMPLETING THE TASK:**
- ✅ CORRECT: list_indices → search_documents → analyze results → finish
- ❌ WRONG: list_indices → finish (YOU HAVE NO DATA!)

**When to set finished=true:**
- ✅ YES: After calling search_documents and getting results (even 0 hits is OK)
- ❌ NO: After only calling list_indices (this is NOT completion!)

---

## QUICK CHECKLIST (Before setting finished=true)

**Did you complete ALL these steps?**
- [ ] Called `list_indices`
- [ ] Called `search_documents` with actual query
- [ ] Retrieved some log data (even if 0 results)
- [ ] Analyzed the data

**If you haven't done ALL 4 steps, DO NOT set finished=true!**

**Remember:**
- `list_indices` alone = You saw the menu but didn't order food
- `search_documents` = Actually getting the food to eat
- **Both are required to complete the task!**

---

## PARAMETER SCHEMAS

**search_documents:**
```json
{
  "index": "sysmon-logs",  // STRING (not array!) Use "log1,log2" for multiple
  "body": {
    "query": {...},        // REQUIRED
    "size": 100,           // Optional - goes OUTSIDE query!
    "_source": [...]       // Optional - goes OUTSIDE query!
  }
}
```

**list_indices:** `{}` (no parameters)

**get_index_mapping:** `{"index": "index-name"}` (STRING, not array)

---

## COMMON ERRORS TO AVOID

**1. Index parameter must be STRING (not array)**
- [X] WRONG: `"index": ["firewall-logs", "sysmon-logs"]`
- [OK] FIX: `"index": "firewall-logs,sysmon-logs"`

**2. size goes OUTSIDE query (MOST COMMON ERROR!)**
- [X] WRONG: `{"body": {"query": {"match_all": {}, "size": 50}}}`
- [OK] FIX: `{"body": {"query": {"match_all": {}}, "size": 50}}`
- Error if wrong: `[match_all] malformed query, expected [END_OBJECT]`
- **This applies to ALL queries including complex bool queries!**

**3. Body must have "query" wrapper**
- [X] WRONG: `{"body": {"term": {"field": "value"}}}`
- [OK] FIX: `{"body": {"query": {"term": {"field": "value"}}}}`

**4. Don't use forbidden parameters**
- [X] WRONG: Adding collapse, version, track_total_hits at params level
- [OK] FIX: Only use "index" and "body" parameters

---

## FEW-SHOT EXAMPLES

### Example 1: Find Malicious Activity

**Step 1:** List indices
```json
{{"tool": "elastic", "operation": "list_indices", "params": {{}}}}
```

**Step 2:** Search with match_all
```json
{{
  "tool": "elastic",
  "operation": "search_documents",
  "params": {{
    "index": "sysmon-logs",
    "body": {{
      "query": {{"match_all": {{}}}},
      "size": 20
    }}
  }}
}}
```

**Step 3:** Search with specific criteria
```json
{{
  "tool": "elastic",
  "operation": "search_documents",
  "params": {{
    "index": "sysmon-logs",
    "body": {{
      "query": {{
        "bool": {{
          "must": [
            {{"term": {{"winlog.event_id": 1}}}},
            {{"match": {{"message": "cmd.exe"}}}}
          ]
        }}
      }},
      "size": 50
    }}
  }}
}}
```

---

### Example 2: Complex Bool Query (must + filter)

```json
{{
  "tool": "elastic",
  "operation": "search_documents",
  "params": {{
    "index": "sysmon-logs,firewall-logs",
    "body": {{
      "query": {{
        "bool": {{
          "must": [
            {{"match": {{"message": "malware"}}}},
            {{"range": {{"@timestamp": {{"gte": "now-72h"}}}}}}
          ],
          "filter": [
            {{"term": {{"event.category": "security"}}}}
          ]
        }}
      }},
      "size": 200   ← size OUTSIDE query!
    }}
  }}
}}
```

---

## KEY TAKEAWAYS

1. **ALWAYS call list_indices first, then search_documents** - Both required!
2. **"index" is a string** - Use `"firewall-logs,sysmon-logs"` not array
3. **size goes OUTSIDE query** - `{"query": {...}, "size": 50}` [OK] NOT `{"query": {..., "size": 50}}` [X]
4. **This applies to ALL queries** - Simple, complex bool, anything!

---

**Last Updated**: 2025-11-25
**Version**: 4.3 (Streamlined - removed redundancy)
**Changelog**:
- v4.3: Major simplification - removed 70% of content, consolidated redundant sections, kept only critical info
- v4.2: Added CRITICAL WARNING at top, MANDATORY WORKFLOW, QUICK CHECKLIST
- v4.1: Added SPECIAL CASE section for bool+size (later removed in v4.3)
- v4.0: Added visual JSON hierarchy
- v3.0: Removed count_documents, added Few-shot examples
**Related**: docs/mcp-tools-reference.md

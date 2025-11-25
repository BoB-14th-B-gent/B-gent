# Velociraptor Endpoint Forensics Strategy

**Tool**: velociraptor
**Purpose**: Endpoint artifact collection and live system investigation
**NOT for**: Searching logs already in a SIEM system

---

## When to Use Velociraptor

**✓ USE Velociraptor for:**
- Collecting artifacts from live endpoints (registry, prefetch, browser history, etc.)
- Endpoint forensics and artifact collection
- Live system investigation
- Retrieving data directly from endpoints

**✗ DO NOT use Velociraptor for:**
- Analyzing logs that are already stored in a SIEM system
- SIEM log analysis (use Elasticsearch instead)
- Searching existing security events

---

## Common Use Cases

### 1. Registry Analysis
Collect Windows registry hives and keys for forensic analysis

### 2. Prefetch Analysis
Extract prefetch files to understand program execution history

### 3. Browser History Collection
Retrieve browser artifacts (history, cookies, cache) from endpoints

### 4. File Collection
Collect specific files from endpoints for analysis

### 5. Process Information
Gather running process information and loaded modules

### 6. Network Connections
Collect active network connections and listening ports

---

## Best Practices

1. **Target specific endpoints** - Use hostname or client ID
2. **Select appropriate artifacts** - Choose VQL artifacts based on investigation needs
3. **Consider performance impact** - Some artifact collections are resource-intensive
4. **Verify client connectivity** - Ensure endpoint is online before collection

---

## Important Notes

- Velociraptor connects to live endpoints via agent
- Collection may take time depending on artifact size
- Some artifacts require elevated privileges
- Always verify you have proper authorization for endpoint access

---

**Last Updated**: 2025-11-24

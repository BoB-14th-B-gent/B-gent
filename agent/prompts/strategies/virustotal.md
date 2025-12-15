# VirusTotal MCP Strategy

## Purpose
Check file hashes, IPs, domains, and URLs against VirusTotal database for threat intelligence.

## Available Operations

### File Hash Lookup:
1. **check_hash** - Check file hash reputation
   - Required params: `hash` (MD5, SHA1, or SHA256)
   - Returns detection results from multiple AV engines

### IP Address Lookup:
1. **check_ip** - Check IP reputation
   - Required params: `ip` (IPv4 address)
   - Returns malicious activity associated with IP

### Domain Lookup:
1. **check_domain** - Check domain reputation
   - Required params: `domain` (e.g., example.com)
   - Returns malicious associations

### URL Lookup:
1. **check_url** - Check URL reputation
   - Required params: `url` (full URL)
   - Returns scan results for the URL

## Common Mistakes to Avoid
- Do NOT include file:// prefix for hash lookups
- Do NOT use full paths - use only the hash value
- Do NOT confuse hash types (MD5=32 chars, SHA1=40 chars, SHA256=64 chars)
- Do NOT check non-public IPs (10.x, 192.168.x, 172.16-31.x)

## Parameter Examples
```json
// Check file hash
{"hash": "d41d8cd98f00b204e9800998ecf8427e"}

// Check IP
{"ip": "8.8.8.8"}

// Check domain
{"domain": "suspicious-domain.com"}

// Check URL
{"url": "https://suspicious-site.com/malware.exe"}
```

## Key Information to Look For
- Detection ratio (X/70 engines detected)
- First/last seen dates
- Community votes
- Associated malware families
- Contacted domains/IPs (for file analysis)

## Expected Workflow
1. Gather IoCs (hashes, IPs, domains) from other analysis
2. check_hash/check_ip/check_domain for each IoC
3. Correlate results to build threat profile

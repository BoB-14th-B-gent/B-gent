# Velociraptor MCP Strategy

## Purpose
Live endpoint forensics - Collect Windows artifacts from running systems via Velociraptor agent.

## Important Notice
This is for LIVE endpoint analysis, NOT disk image analysis. For disk images, use sleuthkit or dissect.

## Required Tool Sequence

### Standard Artifact Collection:
1. **list_clients** - List available Velociraptor clients
   - No required params
   - Returns list of enrolled endpoints with client_id

2. **list_artifacts** - List available artifact collectors
   - No required params
   - Returns available VQL artifacts (Windows.*, Linux.*, etc.)

3. **collect_artifact** - Run artifact collection on endpoint
   - Required params: `client_id`, `artifact_name`
   - Optional: `parameters` (artifact-specific params)

4. **get_flow_results** - Get collection results
   - Required params: `client_id`, `flow_id` (from collect_artifact)

## Common Mistakes to Avoid
- Do NOT use for disk image analysis - this is for live endpoints
- Do NOT forget to get client_id first from list_clients
- Do NOT use arbitrary artifact names - check list_artifacts first
- Do NOT forget to check flow_results after collection

## Parameter Examples
```json
// Step 1: List clients
{}

// Step 2: List available artifacts
{}

// Step 3: Collect artifact
{
  "client_id": "C.1234567890abcdef",
  "artifact_name": "Windows.System.Pslist"
}

// Step 4: Get results
{
  "client_id": "C.1234567890abcdef",
  "flow_id": "F.ABCD1234"
}
```

## Common Artifacts
- Windows.System.Pslist: Running processes
- Windows.Registry.NTUser: User registry hives
- Windows.EventLogs.Evtx: Windows event logs
- Windows.Forensics.Prefetch: Prefetch files
- Windows.Detection.Yara: YARA scanning

## Expected Workflow
1. list_clients -> Get target endpoint client_id
2. list_artifacts -> Identify needed collectors
3. collect_artifact -> Start collection
4. get_flow_results -> Retrieve and analyze results

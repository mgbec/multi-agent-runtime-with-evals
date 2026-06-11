"""Fetch and display A2A call logs from the Orchestrator agent.

Usage:
    python check_a2a.py                     # Last 7 days, output to a2a_report.json
    python check_a2a.py --hours 1           # Last 1 hour
    python check_a2a.py --days 30           # Last 30 days
    python check_a2a.py --output my_report  # Custom output filename (creates my_report.json)
"""
import boto3
import json
import sys
import argparse
import re
from datetime import datetime, timedelta, timezone

REGION = "us-east-1"
LOG_GROUP = "/aws/bedrock-agentcore/runtimes/agentcore_multi_agent_OrchestratorAgent-kbGAc9F1OQ-DEFAULT"

parser = argparse.ArgumentParser(description="Fetch A2A call logs")
parser.add_argument("--hours", type=int, default=None, help="Hours to look back")
parser.add_argument("--days", type=int, default=None, help="Days to look back")
parser.add_argument("--output", type=str, default="a2a_report", help="Output filename (without extension)")
args = parser.parse_args()

if args.days:
    lookback = timedelta(days=args.days)
    label = f"{args.days} day(s)"
elif args.hours:
    lookback = timedelta(hours=args.hours)
    label = f"{args.hours} hour(s)"
else:
    lookback = timedelta(days=7)
    label = "7 days"

output_file = f"{args.output}.json"

client = boto3.client("logs", region_name=REGION)

start_time = int((datetime.now(timezone.utc) - lookback).timestamp() * 1000)

print(f"Fetching A2A calls from last {label}...")
print(f"Log group: {LOG_GROUP}")

response = client.filter_log_events(
    logGroupName=LOG_GROUP,
    startTime=start_time,
    filterPattern="A2A_CALL",
)

a2a_calls = []
events = response.get("events", [])

# Paginate through all results
while True:
    for event in events:
        msg = event["message"]
        try:
            obj = json.loads(msg)
            body = obj.get("body", "")
            trace_id = obj.get("traceId", "")
            span_id = obj.get("spanId", "")
            timestamp_nano = obj.get("timeUnixNano", 0)
            if "A2A_CALL" in str(body):
                a2a_calls.append({
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "body": body,
                    "timestamp_nano": timestamp_nano,
                    "timestamp_ms": event.get("timestamp", 0),
                    "raw": msg,
                })
        except json.JSONDecodeError:
            if "A2A_CALL" in msg:
                a2a_calls.append({
                    "body": msg.strip(),
                    "trace_id": "",
                    "span_id": "",
                    "timestamp_nano": 0,
                    "timestamp_ms": event.get("timestamp", 0),
                    "raw": msg,
                })

    next_token = response.get("nextToken")
    if not next_token:
        break
    response = client.filter_log_events(
        logGroupName=LOG_GROUP,
        startTime=start_time,
        filterPattern="A2A_CALL",
        nextToken=next_token,
    )
    events = response.get("events", [])

if not a2a_calls:
    print(f"\nNo A2A calls found in the last {label}.")
    sys.exit(0)

print(f"Found {len(a2a_calls)} raw A2A log entries.")

# ============================================================================
# Deduplicate and structure calls
# ============================================================================

structured_calls = []
seen_keys = set()

for call in a2a_calls:
    body = call["body"]

    # Determine call type
    call_type = None
    if "A2A_CALL_START" in body:
        call_type = "START"
    elif "A2A_CALL_PAYLOAD" in body:
        call_type = "PAYLOAD"
    elif "A2A_CALL_END" in body:
        call_type = "END"
    elif "A2A_CALL_RESPONSE" in body:
        call_type = "RESPONSE"
    elif "A2A_CALL_ERROR" in body:
        call_type = "ERROR"

    if not call_type:
        continue

    # Extract fields
    target = ""
    arn = ""
    query_length = 0
    response_length = 0
    latency_ms = 0
    query = ""
    response_text = ""

    if "target=" in body:
        m = re.search(r"target=(\w+)", body)
        if m:
            target = m.group(1)
    if "agent=" in body and not target:
        m = re.search(r"agent=(\w+)", body)
        if m:
            target = m.group(1)
    if "arn=" in body:
        m = re.search(r"arn=(arn:aws:bedrock-agentcore:[^\s|]+)", body)
        if m:
            arn = m.group(1)
    if "query_length=" in body:
        m = re.search(r"query_length=(\d+)", body)
        if m:
            query_length = int(m.group(1))
    if "response_length=" in body:
        m = re.search(r"response_length=(\d+)", body)
        if m:
            response_length = int(m.group(1))
    if "latency_ms=" in body:
        m = re.search(r"latency_ms=(\d+)", body)
        if m:
            latency_ms = int(m.group(1))
    if "query=" in body and call_type == "PAYLOAD":
        m = re.search(r"query=(.+?)$", body)
        if m:
            query = m.group(1)
    if "response=" in body and call_type == "RESPONSE":
        m = re.search(r"response=(.+?)$", body)
        if m:
            response_text = m.group(1)[:1000]  # Cap at 1000 chars

    # Deduplicate (same trace + type + target)
    dedup_key = f"{call['trace_id']}:{call_type}:{target}:{call['timestamp_ms'] // 1000}"
    if dedup_key in seen_keys:
        continue
    seen_keys.add(dedup_key)

    ts_str = ""
    if call["timestamp_ms"]:
        ts_str = datetime.fromtimestamp(call["timestamp_ms"] / 1000, tz=timezone.utc).isoformat()

    structured_calls.append({
        "type": call_type,
        "timestamp": ts_str,
        "trace_id": call["trace_id"],
        "span_id": call["span_id"],
        "target": target,
        "arn": arn,
        "query_length": query_length,
        "response_length": response_length,
        "latency_ms": latency_ms,
        "query": query,
        "response": response_text,
    })

# ============================================================================
# Group into sessions (by trace_id)
# ============================================================================

sessions = {}
for call in structured_calls:
    tid = call["trace_id"] or "unknown"
    if tid not in sessions:
        sessions[tid] = []
    sessions[tid].append(call)

# ============================================================================
# Build report
# ============================================================================

# Compute stats
starts = [c for c in structured_calls if c["type"] == "START"]
ends = [c for c in structured_calls if c["type"] == "END"]
errors = [c for c in structured_calls if c["type"] == "ERROR"]
latencies = [c["latency_ms"] for c in ends if c["latency_ms"] > 0]

targets_called = {}
for c in starts:
    t = c["target"]
    targets_called[t] = targets_called.get(t, 0) + 1

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "time_window": label,
    "log_group": LOG_GROUP,
    "summary": {
        "total_a2a_calls": len(starts),
        "total_errors": len(errors),
        "unique_sessions": len(sessions),
        "targets_called": targets_called,
        "latency_avg_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "latency_max_ms": max(latencies) if latencies else 0,
        "latency_min_ms": min(latencies) if latencies else 0,
    },
    "sessions": {},
}

# Add session details
for trace_id, calls in sessions.items():
    session_targets = list(set(c["target"] for c in calls if c["target"]))
    session_latencies = [c["latency_ms"] for c in calls if c["type"] == "END" and c["latency_ms"] > 0]
    session_queries = [c["query"] for c in calls if c["type"] == "PAYLOAD" and c["query"]]
    session_errors = [c for c in calls if c["type"] == "ERROR"]

    report["sessions"][trace_id] = {
        "agents_called": session_targets,
        "total_calls": len([c for c in calls if c["type"] == "START"]),
        "total_latency_ms": sum(session_latencies),
        "queries": session_queries,
        "errors": len(session_errors),
        "calls": calls,
    }

# Security flags
security_flags = []
for call in structured_calls:
    if call["type"] == "START" and call["target"] and call["target"] not in ("specialist", "factchecker"):
        security_flags.append({"severity": "HIGH", "issue": f"Unauthorized target: {call['target']}", "trace": call["trace_id"]})
    if call["type"] == "START" and call["query_length"] > 5000:
        security_flags.append({"severity": "MEDIUM", "issue": f"Large payload ({call['query_length']} chars)", "trace": call["trace_id"]})
    if call["type"] == "END" and call["latency_ms"] > 120000:
        security_flags.append({"severity": "LOW", "issue": f"High latency ({call['latency_ms']}ms)", "trace": call["trace_id"]})
    if call["type"] == "ERROR":
        security_flags.append({"severity": "MEDIUM", "issue": "A2A call error", "trace": call["trace_id"]})

report["security_flags"] = security_flags

# ============================================================================
# Write to file
# ============================================================================

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

# ============================================================================
# Print summary to console
# ============================================================================

print(f"\n{'=' * 60}")
print(f"  A2A REPORT SUMMARY")
print(f"{'=' * 60}")
print(f"  Time window:      {label}")
print(f"  Total A2A calls:  {report['summary']['total_a2a_calls']}")
print(f"  Total errors:     {report['summary']['total_errors']}")
print(f"  Unique sessions:  {report['summary']['unique_sessions']}")
print(f"  Agents called:    {report['summary']['targets_called']}")
if latencies:
    print(f"  Latency (avg):    {report['summary']['latency_avg_ms']}ms")
    print(f"  Latency (max):    {report['summary']['latency_max_ms']}ms")
    print(f"  Latency (min):    {report['summary']['latency_min_ms']}ms")
print(f"  Security flags:   {len(security_flags)}")
if security_flags:
    for flag in security_flags:
        print(f"    [{flag['severity']}] {flag['issue']}")
print(f"\n  Detailed report written to: {output_file}")
print(f"{'=' * 60}")

"""
Ask a question with automatic quality evaluation by the Critic agent.

This script tells the Orchestrator to:
1. Route your question to the appropriate agent (Specialist/Fact Checker)
2. Have the Critic evaluate the response quality
3. Retry if the score is below threshold

Usage:
    python ask_with_critic.py "Your question here"
    python ask_with_critic.py "Explain how Kubernetes networking works"
    python ask_with_critic.py "What is OpenClaw?" "arn:aws:bedrock-agentcore:..."

The response will include the Critic's quality assessment.
"""

import boto3
import json
import sys
import io
import subprocess
import threading
from datetime import datetime, timezone
from botocore.config import Config

# Fix Unicode on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def get_orchestrator_arn():
    """Get the Orchestrator ARN from Terraform output"""
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", "orchestrator_runtime_arn"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: Could not get ARN from terraform output.")
        print("Either run this from the terraform directory, or pass the ARN as the second argument:")
        print('  python ask_with_critic.py "your question" "arn:aws:bedrock-agentcore:..."')
        sys.exit(1)


def progress_indicator(stop_event):
    """Show elapsed time while waiting."""
    import time
    start = datetime.now(timezone.utc)
    while not stop_event.is_set():
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        print(f"\r  Waiting... {elapsed:.0f}s", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 30 + "\r", end="", flush=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    question = sys.argv[1]
    arn = sys.argv[2] if len(sys.argv) > 2 else get_orchestrator_arn()

    # Wrap the question to explicitly request critic evaluation
    prompt = (
        f"This is an important question that needs quality assurance. "
        f"Please get the answer from the specialist, then have the critic evaluate it. "
        f"If the critic scores below 7, retry with the critic's feedback. "
        f"Report the critic's score and any improvements made. "
        f"The question is: {question}"
    )

    print(f"\n{'=' * 60}")
    print(f"  ASK WITH CRITIC")
    print(f"{'=' * 60}")
    print(f"\n  Question: {question}")
    print(f"  Agent: {arn.split('/')[-1]}")
    print(f"  Mode: Specialist + Critic quality loop")
    print()

    client = boto3.client(
        "bedrock-agentcore",
        region_name="us-east-1",
        config=Config(read_timeout=300),
    )

    stop_event = threading.Event()
    spinner = threading.Thread(target=progress_indicator, args=(stop_event,), daemon=True)
    spinner.start()

    start_time = datetime.now(timezone.utc)

    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            qualifier="DEFAULT",
            payload=json.dumps({"prompt": prompt}),
        )
        body = response["response"].read().decode("utf-8")
    except Exception as e:
        stop_event.set()
        spinner.join()
        print(f"  ERROR: {e}")
        sys.exit(1)

    stop_event.set()
    spinner.join()

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

    try:
        result = json.loads(body)
        status = result.get("status", "unknown")
        agent = result.get("agent", "unknown")
        answer = result.get("response", result.get("error", body))
    except json.JSONDecodeError:
        status = "unknown"
        agent = "unknown"
        answer = body

    print(f"  Status: {status}")
    print(f"  Agent: {agent}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"\n{'─' * 60}")
    print(f"  ANSWER:")
    print(f"{'─' * 60}")
    print(f"\n{answer}")
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()

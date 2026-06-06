"""
Simple script to ask the Orchestrator agent a question.

Usage:
    python ask.py "Your question here"
    python ask.py "Is it true that the Earth is 4.5 billion years old?"
    python ask.py "Explain how containers work and verify that Docker uses Linux namespaces"

The Orchestrator will route your question to the appropriate agent(s):
- Simple questions: answers directly
- Analysis questions: routes to Specialist
- Fact-check questions: routes to Fact Checker
- Complex questions: routes to BOTH
"""

import boto3
import json
import sys
import subprocess
from botocore.config import Config


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
        print('  python ask.py "your question" "arn:aws:bedrock-agentcore:..."')
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    prompt = sys.argv[1]
    arn = sys.argv[2] if len(sys.argv) > 2 else get_orchestrator_arn()

    print(f"\nQuestion: {prompt}")
    print(f"Agent: {arn.split('/')[-1]}")
    print("-" * 60)
    print("Waiting for response (may take 30-60s on cold start)...\n")

    client = boto3.client(
        "bedrock-agentcore",
        region_name="us-east-1",
        config=Config(read_timeout=300),
    )

    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        qualifier="DEFAULT",
        payload=json.dumps({"prompt": prompt}),
    )

    body = response["response"].read().decode("utf-8")

    try:
        result = json.loads(body)
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Agent: {result.get('agent', 'unknown')}")
        print(f"\nAnswer:\n{result.get('response', result.get('error', body))}")
    except json.JSONDecodeError:
        print(f"Raw response:\n{body}")


if __name__ == "__main__":
    main()

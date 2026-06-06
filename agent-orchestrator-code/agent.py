from strands import Agent, tool
from strands.models import BedrockModel
from strands.telemetry import Tracer
from typing import Dict, Any
import boto3
import json
import os
import logging
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

# Initialize Strands OTEL tracer for GenAI semantic conventions
# This emits spans for LLM calls, tool usage, and agent reasoning
tracer = Tracer()

# Configure logging for A2A visibility
logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)

# Environment variable for Specialist Agent ARN (required - set by Terraform)
SPECIALIST_ARN = os.getenv("SPECIALIST_ARN")
if not SPECIALIST_ARN:
    raise EnvironmentError("SPECIALIST_ARN environment variable is required")


def invoke_specialist(query: str) -> str:
    """Helper function to invoke specialist agent using boto3"""
    try:
        # Get region from environment (set by AgentCore runtime)
        region = os.getenv("AWS_REGION")
        if not region:
            raise EnvironmentError("AWS_REGION environment variable is required")
        agentcore_client = boto3.client("bedrock-agentcore", region_name=region)

        logger.info(f"A2A_CALL_START | target={SPECIALIST_ARN} | query_length={len(query)}")
        logger.info(f"A2A_CALL_PAYLOAD | query={query[:500]}")

        import time
        start_time = time.time()

        # Invoke specialist agent runtime (using AWS sample format)
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=SPECIALIST_ARN,
            qualifier="DEFAULT",
            payload=json.dumps({"prompt": query}),
        )

        # Handle streaming response (text/event-stream)
        if "text/event-stream" in response.get("contentType", ""):
            result = ""
            for line in response["response"].iter_lines(chunk_size=10):
                if line:
                    line = line.decode("utf-8")
                    # Remove 'data: ' prefix if present
                    if line.startswith("data: "):
                        line = line[6:]
                    result += line
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"A2A_CALL_END | latency_ms={elapsed:.0f} | response_length={len(result)}")
            logger.info(f"A2A_CALL_RESPONSE | response={result[:500]}")
            return result

        # Handle JSON response
        elif response.get("contentType") == "application/json":
            content = []
            for chunk in response.get("response", []):
                content.append(chunk.decode("utf-8"))
            response_data = json.loads("".join(content))
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"A2A_CALL_END | latency_ms={elapsed:.0f} | response_length={len(json.dumps(response_data))}")
            logger.info(f"A2A_CALL_RESPONSE | response={json.dumps(response_data)[:500]}")
            return json.dumps(response_data)

        # Handle other response types
        else:
            response_body = response["response"].read()
            elapsed = (time.time() - start_time) * 1000
            result = response_body.decode("utf-8")
            logger.info(f"A2A_CALL_END | latency_ms={elapsed:.0f} | response_length={len(result)}")
            logger.info(f"A2A_CALL_RESPONSE | response={result[:500]}")
            return result

    except Exception as e:
        import traceback
        logger.error(f"A2A_CALL_ERROR | target={SPECIALIST_ARN} | error={str(e)}")

        error_details = traceback.format_exc()
        return f"Error invoking specialist agent: {str(e)}\nDetails: {error_details}"


@tool
def call_specialist_agent(query: str) -> Dict[str, Any]:
    """
    Call the specialist agent for detailed analysis or complex tasks.
    Use this tool when you need expert analysis or detailed information.

    Args:
        query: The question or task to send to the specialist agent

    Returns:
        The specialist agent's response
    """
    result = invoke_specialist(query)
    return {"status": "success", "content": [{"text": result}]}


def create_orchestrator_agent() -> Agent:
    """Create the orchestrator agent with the tool to call specialist agent"""
    system_prompt = """You are an orchestrator agent.
    You can handle simple queries directly, but for complex analytical tasks,
    you should delegate to the specialist agent using the call_specialist_agent tool.

    Use the specialist agent when:
    - The query requires detailed analysis
    - The query is about complex topics
    - The user explicitly asks for expert analysis

    Handle simple queries (greetings, basic questions) yourself."""

    # Use explicit model to avoid subscription issues with cross-region profiles
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    model = BedrockModel(model_id=model_id)

    return Agent(
        model=model,
        tools=[call_specialist_agent],
        system_prompt=system_prompt,
        name="OrchestratorAgent",
        tracer=tracer,
    )


@app.entrypoint
async def invoke(payload=None):
    """Main entrypoint for orchestrator agent"""
    try:
        # Get the query from payload
        query = (
            payload.get("prompt", "Hello, how are you?")
            if payload
            else "Hello, how are you?"
        )

        # Create and use the orchestrator agent
        agent = create_orchestrator_agent()
        response = agent(query)

        return {
            "status": "success",
            "agent": "orchestrator",
            "response": response.message["content"][0]["text"],
        }

    except Exception as e:
        return {"status": "error", "agent": "orchestrator", "error": str(e)}


if __name__ == "__main__":
    app.run()

from strands import Agent
from strands.models import BedrockModel
from strands.telemetry import Tracer
import os
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

# Initialize Strands OTEL tracer for GenAI semantic conventions
tracer = Tracer()


def create_specialist_agent() -> Agent:
    """Create a specialist agent that handles specific analytical tasks"""
    system_prompt = """You are a specialist analytical agent.
    You are an expert at analyzing data and providing detailed insights.
    When asked questions, provide thorough, well-reasoned responses with specific details.
    Focus on accuracy and completeness in your answers."""

    # Use explicit model to avoid subscription issues with cross-region profiles
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    model = BedrockModel(model_id=model_id)

    return Agent(model=model, system_prompt=system_prompt, name="SpecialistAgent", tracer=tracer)


@app.entrypoint
async def invoke(payload=None):
    """Main entrypoint for specialist agent"""
    try:
        # Get the query from payload
        query = payload.get("prompt", "Hello") if payload else "Hello"

        # Create and use the specialist agent
        agent = create_specialist_agent()
        response = agent(query)

        return {
            "status": "success",
            "agent": "specialist",
            "response": response.message["content"][0]["text"],
        }

    except Exception as e:
        return {"status": "error", "agent": "specialist", "error": str(e)}


if __name__ == "__main__":
    app.run()

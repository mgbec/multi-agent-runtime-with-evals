from strands import Agent, tool
from strands.models import BedrockModel
from typing import Dict, Any, List
import os
import json
import logging
import urllib.request
import urllib.parse
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

# Configure logging
logger = logging.getLogger("specialist")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)

# Tavily API key from environment variable
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


@tool
def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web for current information using Tavily Search API.
    Use this tool when you need up-to-date information, facts about recent events,
    or information about topics not in your training data.

    Args:
        query: The search query to look up on the web
        max_results: Maximum number of results to return (default 5)

    Returns:
        Search results with titles, URLs, and content snippets
    """
    if not TAVILY_API_KEY:
        return {"status": "error", "message": "TAVILY_API_KEY not configured"}

    logger.info(f"WEB_SEARCH | query={query} | max_results={max_results}")

    try:
        payload = json.dumps({
            "query": query,
            "max_results": max_results,
            "include_answer": True,
            "search_depth": "advanced",
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TAVILY_API_KEY}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for r in data.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:500],
            })

        answer = data.get("answer", "")

        logger.info(f"WEB_SEARCH_DONE | query={query} | results_count={len(results)}")

        return {
            "status": "success",
            "answer": answer,
            "results": results,
        }

    except Exception as e:
        logger.error(f"WEB_SEARCH_ERROR | query={query} | error={str(e)}")
        return {"status": "error", "message": str(e)}


def create_specialist_agent() -> Agent:
    """Create a specialist agent that handles specific analytical tasks"""
    system_prompt = """You are a specialist analytical agent with web search capabilities.
    You are an expert at analyzing data and providing detailed insights.
    
    IMPORTANT: You have a web_search tool available. Use it when:
    - The question is about something recent or unfamiliar to you
    - You need current/up-to-date information
    - You're not confident in your knowledge of the topic
    - The user asks about a specific product, project, or event you don't recognize
    
    Always use web_search before saying you don't know something.
    When you search, synthesize the results into a clear, comprehensive answer.
    Cite sources by including relevant URLs."""

    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    model = BedrockModel(model_id=model_id)

    tools = [web_search] if TAVILY_API_KEY else []

    return Agent(model=model, tools=tools, system_prompt=system_prompt, name="SpecialistAgent")


@app.entrypoint
async def invoke(payload=None):
    """Main entrypoint for specialist agent"""
    try:
        query = payload.get("prompt", "Hello") if payload else "Hello"

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

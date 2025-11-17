import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from dotenv import load_dotenv

load_dotenv()
api_base_url = os.getenv("GKE_INFERENCE_ENDPOINT")
MODEL_NAME = os.getenv("MODEL_NAME") 

root_agent = LlmAgent(
    name="root_agent",
    model=LiteLlm(
        model=MODEL_NAME,
        api_base=api_base_url,
    ),
    instruction=(
        """You are a helpful AI assistant designed to provide accurate and useful
        information."""
    ),
    description="An intelligent agent that can answers any questions.",
)

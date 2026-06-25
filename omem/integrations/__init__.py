"""OMem integrations — drop-in memory for popular AI frameworks.

This package exposes adapter classes for external frameworks like LangChain,
CrewAI, MCP, and LlamaIndex.
"""

from .crewai import OMemSharedMemory
from .crewai_adapter import OMemCrewAIAdapter
from .langchain import OMemChatMemory, OMemRetriever
from .llama_index import OMemLlamaIndexAdapter, OMemLlamaIndexRetriever
from .mcp_server import ToolSnippet, mcp
from .mcp_server import omem as mcp_omem

__all__ = [
    "OMemChatMemory",
    "OMemRetriever",
    "OMemSharedMemory",
    "OMemLlamaIndexRetriever",
    "OMemLlamaIndexAdapter",
    "OMemCrewAIAdapter",
    "mcp",
    "mcp_omem",
    "ToolSnippet",
]

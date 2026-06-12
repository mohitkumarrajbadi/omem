"""OMem integrations — drop-in memory for popular AI frameworks.

This package exposes adapter classes for external frameworks like LangChain,
CrewAI, MCP, and LlamaIndex.
"""

from .langchain import OMemChatMemory, OMemRetriever
from .crewai import OMemSharedMemory
from .llama_index import OMemLlamaIndexRetriever, OMemLlamaIndexAdapter
from .crewai_adapter import OMemCrewAIAdapter
from .mcp_server import mcp, omem as mcp_omem, ToolSnippet

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

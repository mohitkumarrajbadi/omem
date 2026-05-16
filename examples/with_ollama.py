# Run this twice — the second run remembers the first.
#
# pip install omem-os requests
# Requires: Ollama running locally (https://ollama.ai)
#   ollama pull llama3.2   # or any model you have
#
# What this shows:
#   - Stores a conversation summary after each session
#   - Recalls relevant past context before each prompt
#   - Memory count grows between runs

import sys
from typing import Optional

import requests

from omem import OMem
from omem.types import MemoryType

OLLAMA_URL = "http://localhost:11434"
MODEL = "llama3.2"  # change to any model you have pulled


def ollama_chat(prompt: str, context: Optional[str] = None) -> str:
    """Send a prompt to Ollama, optionally with recalled memory context."""
    system = "You are a helpful assistant with persistent memory across sessions."
    if context:
        system += f"\n\nRelevant context from previous sessions:\n{context}"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to Ollama at {OLLAMA_URL}")
        print("Make sure Ollama is running: ollama serve")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Ollama HTTP error: {e}")
        print(f"Is the model '{MODEL}' available? Try: ollama pull {MODEL}")
        sys.exit(1)

    data = response.json()
    return data["message"]["content"]


def main() -> None:
    brain = OMem(
        db_path="~/.omem/ollama_demo.db",
        namespace="ollama_demo",
    )

    before_count = len(brain.all())
    print(f"Memory count at start of session: {before_count}")

    user_prompt = "What are the key considerations when choosing a database for a Python web app?"

    # Step 1: recall relevant past context
    recalled = brain.recall(user_prompt, k=3)
    context_str: Optional[str] = None
    if recalled:
        context_str = "\n".join(f"- {m.content}" for m in recalled)
        print(f"\nRecalled {len(recalled)} relevant memory/memories from previous sessions:")
        print(context_str)
    else:
        print("\nNo relevant memories found (first session).")

    # Step 2: call Ollama
    print(f"\nPrompt: {user_prompt}")
    reply = ollama_chat(user_prompt, context=context_str)
    print(f"\nOllama ({MODEL}): {reply[:400]}...")

    # Step 3: store summary for future sessions
    summary = (
        f"Session discussed database selection for Python web apps. "
        f"Key point from response: {reply[:150]}"
    )
    brain.add(summary, mem_type=MemoryType.EPISODIC, importance=0.7)

    after_count = len(brain.all())
    print(f"\nMemory count after session: {after_count} (+{after_count - before_count})")
    print("Run again to see past session context injected into the next prompt.")


if __name__ == "__main__":
    main()

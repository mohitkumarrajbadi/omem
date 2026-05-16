# Run this twice — the second run remembers the first.
#
# pip install omem-os openai
#
# Requires: OPENAI_API_KEY environment variable
#
# What this shows:
#   - Before each OpenAI call, recall relevant memories and inject them
#   - After the response, store the key decision as a new memory
#   - Memory count grows between runs

import os
import sys

from omem import OMem
from omem.types import MemoryType

# Guard: require API key before importing openai
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY environment variable is not set.")
    print("Export it before running: export OPENAI_API_KEY=sk-...")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("OpenAI package not installed. Run: pip install openai")
    sys.exit(1)


def chat_with_memory(client: OpenAI, brain: OMem, user_message: str) -> str:
    """Send a message to OpenAI, injecting recalled memories as context."""

    # Step 1: recall relevant memories before the LLM call
    recalled = brain.recall(user_message, k=3)
    memory_context = "\n".join(f"- {m.content}" for m in recalled)

    system_prompt = "You are a helpful assistant with persistent memory."
    if memory_context:
        system_prompt += (
            f"\n\nRelevant context from memory:\n{memory_context}"
            "\n\nUse this context to give a more informed response."
        )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=300,
    )

    assistant_reply = response.choices[0].message.content or ""

    # Step 2: store the exchange as a memory for future sessions
    brain.add(
        f"User asked: '{user_message[:80]}'. Decision: {assistant_reply[:120]}",
        mem_type=MemoryType.EPISODIC,
        importance=0.6,
    )

    return assistant_reply


def main() -> None:
    brain = OMem(
        db_path="~/.omem/openai_demo.db",
        namespace="openai_demo",
    )
    client = OpenAI(api_key=api_key)

    before_count = len(brain.all())
    print(f"Memory count at start: {before_count}")

    questions = [
        "What programming language should I use for a high-performance API?",
        "Should I use async or sync Python for my new web service?",
    ]

    for q in questions:
        print(f"\nUser: {q}")
        reply = chat_with_memory(client, brain, q)
        print(f"Assistant: {reply[:200]}...")

    after_count = len(brain.all())
    print(f"\nMemory count after session: {after_count} (+{after_count - before_count})")
    print("Run again to see previous decisions injected as context.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
OMem + Ollama - Live AI Agent with Cognitive Memory
Watch an AI agent that ACTUALLY remembers.
Prerequisites:
    pip install requests
    ollama pull gemma3:4b     (or any model you have)
Run:
    python examples/demo_ollama.py
"""

# -- Env vars must be set before ANY other imports (esp. numba/faiss) --
import os

os.environ["NUMBA_DISABLE_JIT"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import sys
import time
import json
import logging
import textwrap
import requests
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omem import OMem, MemoryPriority, MemoryTier  # noqa: E402

# -- Logging -----------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("omem_demo")

# -- Config ------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OMEM_MODEL", "gemma3:4b")
TOP_K_CHAT = int(os.environ.get("OMEM_TOP_K_CHAT", "5"))
TOP_K_MODE = int(os.environ.get("OMEM_TOP_K_MODE", "3"))
STALE_DAYS = int(os.environ.get("OMEM_STALE_DAYS", "45"))
REQUEST_TIMEOUT = int(os.environ.get("OMEM_TIMEOUT", "120"))

# -- Upsert threshold --------------------------------------------------
# OMem's .score is a COMPOSITE score (vector + keyword + importance +
# recency), NOT raw cosine similarity. In practice scores typically
# range 0.0-0.6 for related content and rarely exceed 0.8 even for
# near-duplicates. We set a conservative threshold and only upsert
# when the existing memory is a FACT (not a question or agent reply).
UPSERT_THRESHOLD = float(os.environ.get("OMEM_UPSERT_THRESHOLD", "0.70"))

VALID_MODES = frozenset({"coding", "planning", "chat", "recall", "default"})

# -- ANSI colours (auto-disabled when stdout is not a TTY) -------------
_USE_COLOR = sys.stdout.isatty()


def _c(code: str) -> str:
    return code if _USE_COLOR else ""


C = _c("\033[96m")
G = _c("\033[92m")
Y = _c("\033[93m")
R = _c("\033[91m")
M = _c("\033[95m")
B = _c("\033[1m")
D = _c("\033[2m")
X = _c("\033[0m")

PRI_COLORS: dict[MemoryPriority, str] = {
    MemoryPriority.CORE: R,
    MemoryPriority.HIGH: Y,
    MemoryPriority.NORMAL: G,
    MemoryPriority.LOW: D,
}

MODE_META: dict[str, dict] = {
    "coding": {
        "color": C,
        "instruction": "Respond as a coding assistant helping with implementation.",
    },
    "planning": {
        "color": Y,
        "instruction": "Respond as a strategic advisor helping plan next steps.",
    },
    "chat": {
        "color": G,
        "instruction": "Respond as a friendly assistant having a conversation.",
    },
    "recall": {
        "color": M,
        "instruction": "Respond by recalling all relevant details you can find.",
    },
    "default": {"color": X, "instruction": "Respond helpfully and concisely."},
}

# -- Prompts -----------------------------------------------------------
SYSTEM_PROMPT = textwrap.dedent("""\
    You are an AI assistant with persistent COGNITIVE MEMORY powered by OMem.
    You have access to memories from previous conversations ranked by:
    - Priority: CORE (identity) > HIGH (goals/preferences) > NORMAL (facts) > LOW (filler)
    - Relevance: vector similarity + keyword match + importance + recency

    CRITICAL RULES:
    - If the memory context contains the user's name, ALWAYS use it.
    - If the memory context says where the user works, ALWAYS state it confidently.
    - NEVER say "I don't know your name" if the memory context contains it.
    - NEVER ask for information that already exists in the memory context.
    - Be direct. State facts you remember. Keep responses to 2-4 sentences.
""")

FACT_EXTRACTION_SYSTEM = textwrap.dedent("""\
    You are a fact extractor. Extract only NEW, FACTUAL statements from a user message.

    RULES:
    - Write each fact in third person: "The user's name is Mohit." / "The user works at FICO."
    - ONLY extract statements of fact (name, job, location, preferences, goals, decisions).
    - IGNORE questions ("What is X?"), filler ("ok", "thanks"), and conversational phrases.
    - IGNORE anything that is already a question or request.
    - If the message contains NO new facts, return exactly: []
    - Return ONLY a raw JSON array of strings. No markdown, no explanation, no code fences.

    Examples:
    Input:  "My name is Mohit and I work at FICO."
    Output: ["The user's name is Mohit.", "The user works at FICO."]

    Input:  "What is my name?"
    Output: []

    Input:  "I prefer Python over JavaScript."
    Output: ["The user prefers Python over JavaScript."]

    Input:  "ok sure"
    Output: []
""")

# -- Static seed data --------------------------------------------------
IDENTITY_FACTS = [
    "My name is Mohit Kumar Rajbadi",
    "I am a software engineer specializing in backend systems",
    "My goal is to build an AI startup by 2027",
    "I prefer Python over JavaScript for backend work",
    "I'm currently working on OMem, a cognitive memory OS for AI agents",
    "I use FastAPI for APIs and PostgreSQL for databases",
    "My birthday is March 15",
    "I decided to use Docker for all deployments",
    "To deploy my app: docker compose up -d && docker ps",
    "Yesterday I spent 6 hours debugging a memory leak in production",
]

STALE_MEMORY_SEEDS = [
    "The standup meeting is at 9am tomorrow",
    "Remind me to buy groceries",
    "The wifi password is hunter42",
    "okay sure got it thanks",
    "hmm let me think about that",
]

BANNER = f"""\
{B}{M}
   ######+ ###+   ###+#######+###+   ###+  x  ######+ ##+     ##+      #####+ ###+   ###+ #####+
  ##+===##+####+ ####|##+====+####+ ####|     ##+===##+##|     ##|     ##+==##+####+ ####|##+==##+
  ##|   ##|##+####+##|#####+  ##+####+##|     ##|   ##|##|     ##|     #######|##+####+##|#######|
  ##|   ##|##|+##++##|##+==+  ##|+##++##|     ##|   ##|##|     ##|     ##+==##|##|+##++##|##+==##|
  +######++##| +=+ ##|#######+##| +=+ ##|     +######++#######+#######+##|  ##|##| +=+ ##|##|  ##|
   +=====+ +=+     +=++======++=+     +=+      +=====+ +======++======++=+  +=++=+     +=++=+  +=+
{X}
{D}  Cognitive Memory OS x Local LLM . The AI that actually remembers.
  Model: {MODEL}  .  Upsert threshold: {UPSERT_THRESHOLD}  .  Ctrl+C exits at any time.{X}
"""


# ======================================================================
# Session statistics
# ======================================================================


@dataclass
class SessionStats:
    turns: int = 0
    facts_extracted: int = 0
    memory_updates: int = 0
    memory_inserts: int = 0
    retrieval_times: list[float] = field(default_factory=list)
    llm_times: list[float] = field(default_factory=list)

    def _percentile(self, times: list[float], p: float) -> float:
        if not times:
            return 0.0
        s = sorted(times)
        return s[max(0, int(len(s) * p) - 1)] * 1_000

    def avg_ms(self, times: list[float]) -> float:
        return (sum(times) / len(times) * 1_000) if times else 0.0

    def avg_retrieval_ms(self) -> float:
        return self.avg_ms(self.retrieval_times)

    def avg_llm_ms(self) -> float:
        return self.avg_ms(self.llm_times)

    def p95_retrieval_ms(self) -> float:
        return self._percentile(self.retrieval_times, 0.95)

    def p95_llm_ms(self) -> float:
        return self._percentile(self.llm_times, 0.95)


STATS = SessionStats()


# ======================================================================
# UI helpers
# ======================================================================


def header(title: str) -> None:
    print(f"\n{B}{C}{'=' * 64}{X}")
    print(f"{B}{C}  {title}{X}")
    print(f"{B}{C}{'=' * 64}{X}\n")


def step(msg: str) -> None:
    print(f"  {G}>{X} {msg}")


def truncate(text: str, width: int = 80) -> str:
    return text if len(text) <= width else text[:width] + "..."


def mem_display(m, show_content: bool = True) -> None:
    pc = PRI_COLORS.get(m.priority, X)
    score_str = f"score={G}{m.score:.3f}{X}"
    content_str = f'  "{truncate(m.content, 80)}"' if show_content else ""
    print(
        f"    {pc}[{m.priority.name:6s}]{X} [{C}{m.type.name:10s}{X}] {score_str}{content_str}"
    )


def prompt_enter(msg: str = "Press Enter to continue...") -> None:
    try:
        input(f"\n  {D}{msg}{X}")
    except (KeyboardInterrupt, EOFError):
        pass


def print_retrieved(retrieved: list, mode: str = "", limit: int = 3) -> None:
    if not retrieved:
        return
    label = f" [{mode}]" if mode else ""
    print(f"\n  {D}  +- OMem{label} retrieved {len(retrieved)} memories:{X}")
    for r in retrieved[:limit]:
        print(f'  {D}  | [{r.priority.name}] "{truncate(r.content, 60)}"{X}')
    if len(retrieved) > limit:
        print(f"  {D}  | ... +{len(retrieved) - limit} more{X}")
    print(f"  {D}  +-{X}")


# ======================================================================
# Ollama
# ======================================================================


def check_ollama() -> None:
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        step(f"Ollama connected  model={MODEL}  url={OLLAMA_URL}")
    except requests.exceptions.ConnectionError:
        print(f"  {R}ERROR: Ollama not running! Start with: ollama serve{X}")
        sys.exit(1)


def ollama_chat(prompt: str, system: str = "", model: str = MODEL) -> str:
    """Call Ollama. Never raises. Records LLM latency in STATS."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    t0 = time.perf_counter()
    result = ""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        result = (
            resp.json()
            .get("message", {})
            .get("content", "ERROR: unexpected API response shape")
        )
    except requests.exceptions.ConnectionError:
        result = "ERROR: Ollama not running. Start with: ollama serve"
    except requests.exceptions.Timeout:
        result = f"ERROR: Request timed out after {REQUEST_TIMEOUT}s"
    except requests.exceptions.HTTPError as exc:
        result = f"HTTP ERROR {exc.response.status_code}: {exc}"
    except (KeyError, ValueError) as exc:
        result = f"PARSE ERROR: {exc}"
    except Exception as exc:
        log.exception("Unexpected error in ollama_chat")
        result = f"ERROR: {exc}"
    finally:
        STATS.llm_times.append(time.perf_counter() - t0)
    return result


# ======================================================================
# Memory helpers
# ======================================================================


def _is_question(text: str) -> bool:
    """Return True if the text looks like a question rather than a statement of fact."""
    t = text.strip()
    return t.endswith("?") or t.lower().startswith(
        (
            "what",
            "who",
            "where",
            "when",
            "why",
            "how",
            "is ",
            "are ",
            "do ",
            "does ",
            "can ",
            "could ",
            "tell me",
            "show me",
        )
    )


def memory_context(
    mem: OMem, query: str, mode: str = "default", top_k: int = 5
) -> tuple[str, list]:
    """Run OMem RAG, record latency, return (context_str, results)."""
    t0 = time.perf_counter()
    results = mem.recall(query, top_k=top_k, mode=mode)
    STATS.retrieval_times.append(time.perf_counter() - t0)
    if not results:
        return "", []
    lines = [f"[{r.priority.name} | {r.type.name}] {r.content}" for r in results]
    return "\n".join(lines), results


def smart_add_fact(mem: OMem, fact: str) -> str:
    """
    Upsert a FACT memory.

    The key fixes vs. the previous version:
    1. We only upsert when the best existing match is ALSO a fact-type
       memory (not a question, not an agent reply). This prevents
       "What is my name?" from overwriting "The user's name is Mohit."
    2. We calibrate the threshold against OMem's actual composite score
       range. Scores > 1.0 are impossible for true cosine but ARE
       possible in OMem's weighted composite - so we use a threshold
       that only triggers for near-verbatim matches (~0.70 composite).
    3. Questions are never eligible for upsert, only plain fact inserts.
    """
    if _is_question(fact):
        # Questions carry zero factual value - skip storing them entirely
        return ""

    existing = mem.recall(fact, top_k=1, mode="recall")

    if existing:
        best = existing[0]
        candidate = mem.get(best.id)

        # Only upsert if the matching memory is itself a stored fact
        # (not a question and not an agent sentence fragment)
        is_fact_memory = (
            candidate is not None
            and not _is_question(candidate.content)
            and not candidate.content.startswith(
                '"'
            )  # agent replies stored with leading "
        )

        # Use a stricter threshold: only merge near-verbatim duplicates.
        # We intentionally cap at a maximum of 0.85 to avoid the
        # scores > 1.0 issue (composite scoring overflow) overwriting
        # distinct facts.
        effective_score = min(best.score, 0.85)

        if is_fact_memory and effective_score >= UPSERT_THRESHOLD:
            if candidate.content.strip().lower() != fact.strip().lower():
                candidate.content = fact
                candidate.timestamp = time.time()
                candidate.last_accessed = time.time()
                STATS.memory_updates += 1
                print(f'  {Y}  Memory updated: "{truncate(fact, 55)}"{X}')
            return best.id

    STATS.memory_inserts += 1
    return mem.add(fact, source="user_fact")


def extract_and_store_facts(mem: OMem, user_input: str) -> None:
    """
    Extract facts from user input via LLM, store each one via smart_add_fact.
    Questions and filler produce [] and are silently skipped.
    Falls back to raw storage only if extraction itself crashes.
    """
    # Fast-path: if it's purely a question, skip the extraction LLM call entirely
    if _is_question(user_input) and len(user_input.split()) < 8:
        log.debug("Skipping fact extraction for question: %s", user_input)
        return

    extraction_prompt = (
        f"Extract factual statements from this message as a JSON array of strings.\n"
        f'Message: "{user_input}"'
    )
    raw = ollama_chat(extraction_prompt, system=FACT_EXTRACTION_SYSTEM)

    # Strip markdown fences defensively
    raw = raw.strip()
    for fence in ("```json", "```"):
        raw = raw.lstrip(fence)
    raw = raw.rstrip("```").strip()

    extracted: list[str] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            extracted = [f for f in parsed if isinstance(f, str) and f.strip()]
    except (json.JSONDecodeError, ValueError):
        log.debug("Fact extraction parse failed. Raw: %s", raw)

    if extracted:
        for fact in extracted:
            result_id = smart_add_fact(mem, fact.strip())
            if result_id:
                STATS.facts_extracted += 1
                print(f'  {G}  Fact stored: "{truncate(fact, 60)}"{X}')
    # If nothing extracted, we intentionally store nothing.
    # Questions and filler should NOT pollute the memory store.


def store_agent_reply(mem: OMem, reply: str) -> None:
    """
    Store an agent reply as a LOW-priority episodic memory.
    Agent replies are ALWAYS fresh inserts - never upserted -
    because they are episodic records, not updateable facts.
    We skip replies that are errors or very short.
    """
    if reply.startswith("ERROR") or len(reply.strip()) < 20:
        return
    mem.add(reply, source="assistant")
    STATS.memory_inserts += 1


def count_by_priority(memories: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in memories:
        counts[m.priority.name] = counts.get(m.priority.name, 0) + 1
    return counts


def build_prompt(
    context_str: str,
    user_input: str,
    mode: str = "default",
    extra_instruction: str = "",
) -> str:
    mode_label = (
        f"retrieved in '{mode}' mode"
        if mode != "default"
        else "from your cognitive memory"
    )
    parts = [
        f"Memory context ({mode_label}):",
        context_str or "(no relevant memories found)",
    ]
    if extra_instruction:
        parts.append(extra_instruction)
    parts += [
        f"User says: {user_input}",
        "Respond using the memory context above. Reference specific facts. Be direct.",
    ]
    return "\n".join(parts)


# ======================================================================
# Phase 1 - Identity seeding
# ======================================================================


def phase1_identity_seeding(mem: OMem) -> None:
    header("PHASE 1: Identity Seeding - Teaching the Agent Who You Are")
    print(f"  {D}Watch how OMem auto-classifies each memory by priority.{X}\n")

    for fact in IDENTITY_FACTS:
        mid = mem.add(fact)
        m = mem.get(mid)
        pc = PRI_COLORS.get(m.priority, X)
        tier_info = f" {R}[IMMUNE]{X}" if m.tier == MemoryTier.CORE else ""
        print(
            f"  {pc}> {m.priority.name:6s}{X} [{C}{m.type.name:10s}{X}]"
            f'{tier_info}  "{truncate(fact, 60)}"'
        )

    all_mems = mem.brain.kv.all()
    pri_counts = count_by_priority(all_mems)
    print(
        f"\n  {B}Result:{X} Stored {G}{len(IDENTITY_FACTS)}{X} memories - "
        f"{R}{pri_counts.get('CORE', 0)} CORE{X} (immune), "
        f"{Y}{pri_counts.get('HIGH', 0)} HIGH{X}, rest NORMAL"
    )
    prompt_enter("Press Enter to continue to live chat...")


# ======================================================================
# Phase 2 - Live chat
# ======================================================================


def phase2_live_chat(mem: OMem) -> None:
    header("PHASE 2: Live Chat - The Agent Remembers & Updates On-The-Go")
    print(
        f"  {D}Facts you state are extracted and stored. Questions are not stored.{X}"
    )
    print(f"  {D}Try these in order:{X}")
    print(f"  {D}  1. 'I work at FICO'              -> fact stored{X}")
    print(f"  {D}  2. 'Where do I work?'            -> recalled from memory{X}")
    print(f"  {D}  3. 'Actually I moved to OpenAI'  -> fact updated in memory{X}")
    print(f"  {D}  4. 'Where do I work now?'        -> reflects update{X}")
    print(f"  {D}Type 'next' to advance to the next phase.{X}\n")

    while True:
        try:
            user_input = input(f"  {B}{G}You:{X} ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not user_input:
            continue
        if user_input.lower() == "next":
            break

        STATS.turns += 1
        extract_and_store_facts(mem, user_input)

        context_str, retrieved = memory_context(
            mem, user_input, mode="chat", top_k=TOP_K_CHAT
        )
        print_retrieved(retrieved, mode="chat")

        prompt = build_prompt(context_str, user_input, mode="chat")
        print(f"\n  {B}{M}Agent:{X} ", end="", flush=True)
        response = ollama_chat(prompt, SYSTEM_PROMPT)
        print(response)

        store_agent_reply(mem, response)
        print()


# ======================================================================
# Phase 3 - Mode-aware RAG
# ======================================================================


def phase3_mode_aware_rag(mem: OMem) -> None:
    header("PHASE 3: Mode-Aware RAG - Same Question, Different Thinking")
    print(f"  {D}Different modes surface different memories for the same query.{X}\n")

    test_query = "Tell me about my work and projects"

    for mode, meta in MODE_META.items():
        if mode == "default":
            continue
        context_str, retrieved = memory_context(
            mem, test_query, mode=mode, top_k=TOP_K_MODE
        )
        color = meta["color"]
        print(f'  {B}{color}=== mode="{mode}" ==={X}')
        print(f"  {D}Retrieved:{X}")
        for r in retrieved:
            mem_display(r)
        prompt = build_prompt(
            context_str, test_query, mode=mode, extra_instruction=meta["instruction"]
        )
        response = ollama_chat(prompt, SYSTEM_PROMPT)
        print(f"  {B}Agent:{X} {response}\n")

    prompt_enter("Press Enter to continue to the forgetting demo...")


# ======================================================================
# Phase 4 - Intelligent forgetting
# ======================================================================


def phase4_intelligent_forgetting(mem: OMem) -> None:
    header("PHASE 4: Intelligent Forgetting - The Agent Cleans Up")
    print(
        f"  {D}Adding stale memories then watching the forgetting engine prune them.{X}\n"
    )

    now = time.time()
    old_ids = []

    for content in STALE_MEMORY_SEEDS:
        mid = mem.add(content)
        old_ids.append(mid)
        m = mem.get(mid)
        step(f'Added: "{truncate(content, 55)}" -> {m.priority.name}')

    for mid in old_ids:
        m = mem.get(mid)
        if m and m.priority != MemoryPriority.CORE:
            m.timestamp = now - (STALE_DAYS * 86_400)
            m.last_accessed = 0.0
            if m.priority == MemoryPriority.LOW:
                m.importance = 0.15

    print(f"\n  {D}[clock] Simulating {STALE_DAYS} days passing...{X}\n")

    result = mem.forget()
    step("Forget sweep complete:")
    print(f"    {G}Kept:{X}        {result.kept}")
    print(f"    {Y}Archived:{X}    {len(result.archived)}")
    print(f"    {R}Deleted:{X}     {len(result.deleted)}")
    print(f"    {M}Core immune:{X} {result.core_immune}")

    if result.archived:
        print(f"\n  {D}Archived (recoverable via mem.restore):{X}")
        for aid in result.archived:
            m = mem.get(aid)
            if m:
                print(f'    {D}Archived: "{truncate(m.content, 55)}"{X}')

    print(f"\n  {B}Testing identity recall after forgetting:{X}")
    context_str, _ = memory_context(mem, "What do you know about me?", mode="recall")
    prompt = build_prompt(
        context_str,
        "What do you still know about me?",
        mode="recall",
        extra_instruction=(
            "The forgetting engine just ran. "
            "List specific facts you still remember about the user."
        ),
    )
    print(f"\n  {B}{M}Agent:{X} ", end="", flush=True)
    print(ollama_chat(prompt, SYSTEM_PROMPT))
    prompt_enter("Press Enter to continue to the explainability demo...")


# ======================================================================
# Phase 5 - Explainability
# ======================================================================


def phase5_explainability(mem: OMem) -> None:
    header("PHASE 5: Explainability - WHY Did It Remember That?")
    print(f"  {D}5-signal scoring breakdown per retrieved memory.{X}\n")

    inspect_query = "What does the user work on?"
    explanations = mem.inspect(inspect_query, top_k=3)

    if not explanations:
        print(f"  {Y}No memories yet. Run Phase 1 first to seed identity facts.{X}\n")
        return

    for i, exp in enumerate(explanations, 1):
        m = mem.get(exp.memory_id)
        content = truncate(m.content, 60) if m else "?"
        priority = m.priority.name if m else "?"
        print(f'  {B}#{i} [{priority}]{X} "{content}"')
        print(f"    +-- {C}Vector Similarity : {exp.vector_score:>8.4f}{X}")
        print(f"    |   {C}Keyword Match     : {exp.keyword_score:>8.4f}{X}")
        print(f"    |   {C}Importance        : {exp.importance_score:>8.4f}{X}")
        print(f"    |   {C}Recency           : {exp.recency_score:>8.4f}{X}")
        print(f"    |   {C}Frequency Bonus   : {exp.frequency_bonus:>8.4f}{X}")
        print(f"    +-- {B}{G}Final Score      : {exp.final_score:>8.4f}{X}")
        print()


# ======================================================================
# Phase 6 - Full interactive
# ======================================================================


def phase6_interactive(mem: OMem) -> None:
    header("PHASE 6: Full Interactive Mode")
    print(f"  {D}Everything you say is fact-extracted and stored.{X}")
    print(f"  {D}Questions are never stored - only facts are.{X}\n")
    print(f"  {B}Commands:{X}")
    print(f"    {C}/memories{X}      - show stored memories")
    print(f"    {C}/forget{X}        - run forgetting engine")
    print(f"    {C}/inspect [q]{X}   - scoring breakdown for query q")
    print(f"    {C}/mode <name>{X}   - switch mode ({'/'.join(sorted(VALID_MODES))})")
    print(f"    {C}/stats{X}         - memory + session stats")
    print(f"    {C}/bench{X}         - retrieval latency benchmark")
    print(f"    {C}/quit{X}          - return to main menu\n")

    current_mode = "default"
    last_query = ""

    while True:
        try:
            user_input = input(f"  {B}{G}You [{current_mode}]:{X} ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not user_input:
            continue

        # -- Commands --------------------------------------------------
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd == "/quit":
                break
            elif cmd == "/memories":
                _cmd_memories(mem)
            elif cmd == "/forget":
                _cmd_forget(mem)
            elif cmd == "/inspect":
                _cmd_inspect(mem, arg or last_query or "recent facts")
            elif cmd == "/mode":
                current_mode = _cmd_mode(current_mode, arg)
            elif cmd == "/stats":
                _cmd_stats(mem, current_mode)
            elif cmd == "/bench":
                _cmd_bench(mem)
            else:
                print(
                    f"  {D}Unknown command. Available: /memories /forget /inspect "
                    f"/mode /stats /bench /quit{X}\n"
                )
            continue

        # -- Chat path -------------------------------------------------
        STATS.turns += 1
        last_query = user_input

        # Extract and persist facts BEFORE retrieval so the answer
        # to "Where do I work?" immediately reflects what was just stated.
        extract_and_store_facts(mem, user_input)

        context_str, retrieved = memory_context(
            mem, user_input, mode=current_mode, top_k=TOP_K_CHAT
        )
        if retrieved:
            print(f"  {D}  OMem [{current_mode}] -> {len(retrieved)} memories{X}")

        prompt = build_prompt(context_str, user_input, mode=current_mode)
        print(f"  {B}{M}Agent:{X} ", end="", flush=True)
        response = ollama_chat(prompt, SYSTEM_PROMPT)
        print(response)

        # Agent replies: always fresh inserts, never upserted
        store_agent_reply(mem, response)
        print()


# ======================================================================
# Command handlers
# ======================================================================


def _cmd_memories(mem: OMem) -> None:
    all_m = mem.brain.kv.all()
    active = [m for m in all_m if m.active and m.tier != MemoryTier.FORGOTTEN]
    archived = [m for m in all_m if m.tier == MemoryTier.ARCHIVE]
    print(
        f"\n  {B}Memory Store:{X} {G}{len(active)} active{X}, {D}{len(archived)} archived{X}\n"
    )
    # Sort: CORE first, then by timestamp descending
    priority_order = {
        MemoryPriority.CORE: 0,
        MemoryPriority.HIGH: 1,
        MemoryPriority.NORMAL: 2,
        MemoryPriority.LOW: 3,
    }
    sorted_mems = sorted(
        active, key=lambda m: (priority_order.get(m.priority, 9), -m.timestamp)
    )
    for m in sorted_mems[:25]:
        pc = PRI_COLORS.get(m.priority, X)
        content = truncate(m.content, 65)
        print(
            f'    {pc}[{m.priority.name:6s}]{X} [{C}{m.type.name:10s}{X}] "{content}"'
        )
    if len(active) > 25:
        print(f"    {D}... and {len(active) - 25} more{X}")
    print()


def _cmd_forget(mem: OMem) -> None:
    result = mem.forget()
    print(
        f"\n  {B}Forget sweep:{X} "
        f"{G}kept={result.kept}{X}  "
        f"{Y}archived={len(result.archived)}{X}  "
        f"{R}deleted={len(result.deleted)}{X}  "
        f"{M}core_immune={result.core_immune}{X}\n"
    )


def _cmd_inspect(mem: OMem, query: str) -> None:
    print(f'  {D}Inspecting query: "{truncate(query, 55)}"{X}\n')
    exps = mem.inspect(query, top_k=5)
    if not exps:
        print(f"  {D}No memories found for that query.{X}\n")
        return
    for i, exp in enumerate(exps, 1):
        m = mem.get(exp.memory_id)
        content = truncate(m.content, 50) if m else "?"
        pri = m.priority.name if m else "?"
        pc = PRI_COLORS.get(m.priority, X) if m else X
        print(
            f"  {pc}#{i} [{pri}]{X} [{G}{exp.final_score:.4f}{X}] "
            f"v={exp.vector_score:.3f} k={exp.keyword_score:.3f} "
            f"i={exp.importance_score:.3f} r={exp.recency_score:.3f} "
            f'"{content}"'
        )
    print()


def _cmd_mode(current_mode: str, arg: str) -> str:
    if not arg:
        print(f"  {R}Usage: /mode <{'|'.join(sorted(VALID_MODES))}>{X}\n")
        return current_mode
    new = arg.lower()
    if new in VALID_MODES:
        print(f"  {M}Mode: {current_mode} -> {new}{X}\n")
        return new
    print(f"  {R}Unknown mode '{arg}'. Valid: {', '.join(sorted(VALID_MODES))}{X}\n")
    return current_mode


def _cmd_stats(mem: OMem, current_mode: str) -> None:
    all_m = mem.brain.kv.all()
    active = sum(1 for m in all_m if m.active)
    by_pri = count_by_priority(all_m)
    by_type: dict[str, int] = {}
    for m in all_m:
        by_type[m.type.name] = by_type.get(m.type.name, 0) + 1

    div = f"  {B}{C}{'-' * 50}{X}"
    print(f"\n{div}")
    print(f"  {B}Memory Statistics{X}")
    print(div)
    print(f"    Total          : {len(all_m)}  (active={active})")
    print(
        "    By Priority    : "
        + "  ".join(
            f"{PRI_COLORS.get(MemoryPriority[k], X)}{k}={v}{X}"
            for k, v in sorted(by_pri.items())
            if k in MemoryPriority.__members__
        )
    )
    print(
        "    By Type        : "
        + "  ".join(f"{k}={v}" for k, v in sorted(by_type.items()))
    )
    print(f"    Current Mode   : {current_mode}")
    print(f"\n  {B}Session Benchmarks{X}")
    print(f"    Chat turns     : {STATS.turns}")
    print(f"    Facts extracted: {STATS.facts_extracted}")
    print(f"    Mem inserts    : {STATS.memory_inserts}")
    print(f"    Mem updates    : {STATS.memory_updates}")
    if STATS.retrieval_times:
        print(
            f"    RAG latency    : "
            f"avg={STATS.avg_retrieval_ms():.1f}ms  "
            f"p95={STATS.p95_retrieval_ms():.1f}ms  "
            f"n={len(STATS.retrieval_times)}"
        )
    if STATS.llm_times:
        print(
            f"    LLM latency    : "
            f"avg={STATS.avg_llm_ms():.1f}ms  "
            f"p95={STATS.p95_llm_ms():.1f}ms  "
            f"n={len(STATS.llm_times)}"
        )
    print()


def _cmd_bench(mem: OMem) -> None:
    header("Quick Retrieval Benchmark")
    queries = [
        "What is my name?",
        "What tech stack do I use?",
        "What are my career goals?",
        "How do I deploy my app?",
        "What language do I prefer?",
    ]
    results: dict[str, list[float]] = {m: [] for m in VALID_MODES}
    total = len(queries) * len(VALID_MODES)
    done = 0

    for mode in VALID_MODES:
        for q in queries:
            t0 = time.perf_counter()
            mem.recall(q, top_k=TOP_K_CHAT, mode=mode)
            elapsed = (time.perf_counter() - t0) * 1_000
            results[mode].append(elapsed)
            done += 1
            print(
                f"  {D}[{done:>2}/{total}] {mode:<10} "
                f'"{truncate(q, 35)}"  {elapsed:.1f}ms{X}'
            )

    print(f"\n  {B}Summary by mode:{X}")
    for mode in sorted(VALID_MODES):
        times = results[mode]
        avg = sum(times) / len(times)
        color = MODE_META.get(mode, {}).get("color", X)
        print(
            f"    {color}{mode:<12}{X}  "
            f"avg={avg:>6.1f}ms  "
            f"min={min(times):>6.1f}ms  "
            f"max={max(times):>6.1f}ms"
        )
    print()


# ======================================================================
# Main menu
# ======================================================================

PHASES: dict[str, tuple[str, object]] = {
    "1": ("Identity Seeding", phase1_identity_seeding),
    "2": ("Live Chat (fact updates)", phase2_live_chat),
    "3": ("Mode-Aware RAG", phase3_mode_aware_rag),
    "4": ("Intelligent Forgetting", phase4_intelligent_forgetting),
    "5": ("Explainability / Audit", phase5_explainability),
    "6": ("Full Interactive Mode", phase6_interactive),
}


def print_menu(mem: OMem) -> None:
    all_m = mem.brain.kv.all()
    active = sum(1 for m in all_m if m.active)
    pri = count_by_priority(all_m)
    print(f"\n{B}{C}{'=' * 52}{X}")
    print(
        f"{B}{C}  OMem Demo - Main Menu{X}  "
        f"{D}({active} memories . "
        f"{R}CORE={pri.get('CORE', 0)}{D} "
        f"{Y}HIGH={pri.get('HIGH', 0)}{D} "
        f"NORMAL={pri.get('NORMAL', 0)}){X}"
    )
    print(f"{B}{C}{'=' * 52}{X}")
    for key, (label, _) in PHASES.items():
        print(f"    {C}[{key}]{X}  {label}")
    print(f"    {C}[a]{X}  Run all phases in order")
    print(f"    {C}[r]{X}  Reset memory store")
    print(f"    {C}[s]{X}  Session stats")
    print(f"    {C}[q]{X}  Quit")
    print(f"{B}{C}{'-' * 52}{X}\n")


def run_menu(mem: OMem) -> None:
    while True:
        print_menu(mem)
        try:
            choice = (
                input(f"  {B}Select:{X} ").strip().lower()
            )  # .lower() fixes "Quit" / "Q"
        except (KeyboardInterrupt, EOFError):
            break

        if choice == "q":
            break
        elif choice == "a":
            for key in ["1", "2", "3", "4", "5", "6"]:
                label, fn = PHASES[key]
                print(f"\n  {D}> Starting: {label}{X}")
                fn(mem)
        elif choice == "r":
            confirm = (
                input(
                    f"  {R}Reset ALL memories? This cannot be undone. Type 'yes' to confirm:{X} "
                )
                .strip()
                .lower()
            )
            if confirm == "yes":
                mem.__init__()
                print(f"  {G}Memory store reset.{X}\n")
            else:
                print(f"  {D}Reset cancelled.{X}\n")
        elif choice == "s":
            _cmd_stats(mem, "-")
        elif choice in PHASES:
            _, fn = PHASES[choice]
            fn(mem)
        else:
            print(f"  {R}Invalid choice. Enter 1-6, a, r, s, or q.{X}\n")


# ======================================================================
# Session summary
# ======================================================================


def print_session_summary(mem: OMem) -> None:
    all_m = mem.brain.kv.all()
    total = len(all_m)
    core_c = sum(1 for m in all_m if m.priority == MemoryPriority.CORE)
    high_c = sum(1 for m in all_m if m.priority == MemoryPriority.HIGH)
    r_avg = f"{STATS.avg_retrieval_ms():.0f}ms" if STATS.retrieval_times else "-"
    l_avg = f"{STATS.avg_llm_ms():.0f}ms" if STATS.llm_times else "-"
    r_p95 = f"{STATS.p95_retrieval_ms():.0f}ms" if STATS.retrieval_times else "-"
    l_p95 = f"{STATS.p95_llm_ms():.0f}ms" if STATS.llm_times else "-"

    print(f"""
{B}{M}
  +==============================================================+
  |  Session complete.                                           |
  +==============================================================+
  |  {G}Memories stored   : {total:>4}{M}                                 |
  |  {R}Core (immune)     : {core_c:>4}{M}                                 |
  |  {Y}High priority     : {high_c:>4}{M}                                 |
  +==============================================================+
  |  {C}Chat turns        : {STATS.turns:>4}{M}                                 |
  |  {C}Facts extracted   : {STATS.facts_extracted:>4}{M}                                 |
  |  {C}Memory inserts    : {STATS.memory_inserts:>4}{M}                                 |
  |  {C}Memory updates    : {STATS.memory_updates:>4}{M}                                 |
  +==============================================================+
  |  {C}RAG  avg/p95      : {r_avg:>6} / {r_p95:>6}{M}                      |
  |  {C}LLM  avg/p95      : {l_avg:>6} / {l_p95:>6}{M}                      |
  +==============================================================+
  |  "OMem - AI memory that evolves, not accumulates."           |
  +==============================================================+
{X}""")


# ======================================================================
# Entry point
# ======================================================================


def main() -> None:
    print(BANNER)
    check_ollama()
    mem = OMem()
    try:
        run_menu(mem)
    except KeyboardInterrupt:
        pass
    finally:
        print_session_summary(mem)


if __name__ == "__main__":
    main()

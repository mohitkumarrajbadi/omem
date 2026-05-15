"""Knowledge Graph — Entity Extraction & Semantic Linking.

Upgrades the existing CausalGraph into a full Knowledge Graph with:
- Automatic entity extraction (Person, Technology, Project, Org, Location)
- Typed semantic edges (USES, WORKS_ON, PREFERS, DECIDED, etc.)
- Multi-hop graph traversal for relational queries

When mem.add() is called, entities are extracted and linked.
When mem.rag() is called, graph traversal augments vector search.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class EntityType(Enum):
    """Types of entities extracted from memory content."""

    PERSON = "person"
    TECHNOLOGY = "technology"
    PROJECT = "project"
    ORGANIZATION = "organization"
    LOCATION = "location"
    CONCEPT = "concept"


class EdgeType(Enum):
    """Types of relationships between entities."""

    USES = "uses"
    WORKS_ON = "works_on"
    WORKS_AT = "works_at"
    PREFERS = "prefers"
    DECIDED = "decided"
    KNOWS = "knows"
    LOCATED_AT = "located_at"
    RELATED_TO = "related_to"
    CREATED = "created"
    DEPENDS_ON = "depends_on"


@dataclass
class Entity:
    """A named entity extracted from memory content."""

    name: str
    type: EntityType
    memory_ids: List[str] = field(default_factory=list)
    mention_count: int = 1

    def __hash__(self):
        return hash((self.name.lower(), self.type))

    def __eq__(self, other):
        return (
            isinstance(other, Entity)
            and self.name.lower() == other.name.lower()
            and self.type == other.type
        )


@dataclass
class Edge:
    """A typed, weighted edge between two entities."""

    source: str  # Entity name (lowercase)
    target: str  # Entity name (lowercase)
    edge_type: EdgeType
    weight: float = 1.0
    memory_id: str = ""  # The memory that created this edge
    label: str = ""


# ── Entity extraction patterns ──

# Technology names (common programming languages, frameworks, tools)
_TECH_PATTERNS = re.compile(
    r"\b("
    r"Python|JavaScript|TypeScript|Java|Go|Rust|C\+\+|Ruby|PHP|Swift|Kotlin|"
    r"React|Vue|Angular|Next\.?js|FastAPI|Flask|Django|Express|Spring|Rails|"
    r"Docker|Kubernetes|K8s|AWS|GCP|Azure|Redis|PostgreSQL|Postgres|MySQL|"
    r"MongoDB|SQLite|FAISS|Git|GitHub|GitLab|Nginx|Apache|Linux|macOS|"
    r"Node\.?js|TensorFlow|PyTorch|NumPy|Pandas|Scikit|ONNX|Numba|"
    r"GraphQL|REST|gRPC|Kafka|RabbitMQ|Terraform|Ansible|CI/CD|"
    r"Railway|Vercel|Heroku|Netlify|Supabase|Firebase"
    r")\b",
    re.IGNORECASE,
)

# Organization patterns
_ORG_PATTERNS = re.compile(
    r"\b("
    r"Google|Microsoft|Apple|Amazon|Meta|Facebook|Netflix|Uber|Airbnb|"
    r"OpenAI|Anthropic|DeepMind|FICO|NVIDIA|Intel|AMD|IBM|Oracle|"
    r"Stripe|Shopify|Salesforce|Adobe|Twitter|X Corp|LinkedIn|"
    r"MIT|Stanford|Berkeley|Harvard|"
    r"(?:[A-Z][a-z]+ (?:Inc|Corp|Ltd|LLC|Co|Foundation|Labs?)\.?)"
    r")\b"
)

# Person name heuristics (after "my name is", "I am", etc.)
_PERSON_PATTERNS = [
    re.compile(
        r"(?:my name is|i am|i'm|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:told|asked|met|know|called)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),
]

# Location patterns
_LOCATION_PATTERNS = re.compile(
    r"\b(?:in|at|from|to|near)\s+("
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*"
    r")\b"
)

# Relationship detection patterns
_RELATION_PATTERNS = {
    EdgeType.USES: re.compile(
        r"\b(?:use|using|used|uses|built with|built on|runs on|powered by)\b",
        re.IGNORECASE,
    ),
    EdgeType.PREFERS: re.compile(
        r"\b(?:prefer|prefers|preferred|favorite|favourite|love|likes?)\b",
        re.IGNORECASE,
    ),
    EdgeType.WORKS_ON: re.compile(
        r"\b(?:working on|work on|building|developing|creating|maintaining)\b",
        re.IGNORECASE,
    ),
    EdgeType.WORKS_AT: re.compile(
        r"\b(?:work at|works at|employed at|job at|role at|position at)\b",
        re.IGNORECASE,
    ),
    EdgeType.DECIDED: re.compile(
        r"\b(?:decided|chose|chosen|picked|selected|switched to|migrated to)\b",
        re.IGNORECASE,
    ),
    EdgeType.CREATED: re.compile(
        r"\b(?:created|built|made|wrote|developed|designed|invented)\b", re.IGNORECASE
    ),
    EdgeType.DEPENDS_ON: re.compile(
        r"\b(?:depends on|requires|needs|relies on|based on)\b", re.IGNORECASE
    ),
}


def extract_entities(content: str) -> List[Entity]:
    """Extract named entities from memory content using regex patterns.

    Returns a list of Entity objects with type classification.
    Fast, runs in microseconds, no LLM needed.
    """
    entities: List[Entity] = []
    seen: Set[str] = set()

    # Extract person names
    for pattern in _PERSON_PATTERNS:
        for match in pattern.finditer(content):
            name = match.group(1).strip()
            key = name.lower()
            if key not in seen and len(name) > 1:
                entities.append(Entity(name=name, type=EntityType.PERSON))
                seen.add(key)

    # Extract technology names
    for match in _TECH_PATTERNS.finditer(content):
        name = match.group(1)
        key = name.lower()
        if key not in seen:
            entities.append(Entity(name=name, type=EntityType.TECHNOLOGY))
            seen.add(key)

    # Extract organization names
    for match in _ORG_PATTERNS.finditer(content):
        name = match.group(1).strip()
        key = name.lower()
        if key not in seen and len(name) > 2:
            entities.append(Entity(name=name, type=EntityType.ORGANIZATION))
            seen.add(key)

    # Extract locations (simpler heuristic)
    for match in _LOCATION_PATTERNS.finditer(content):
        name = match.group(1).strip()
        key = name.lower()
        if (
            key not in seen
            and len(name) > 2
            and key not in {e.name.lower() for e in entities}
        ):
            entities.append(Entity(name=name, type=EntityType.LOCATION))
            seen.add(key)

    return entities


def detect_relationships(content: str) -> List[EdgeType]:
    """Detect relationship types present in the content."""
    found = []
    for edge_type, pattern in _RELATION_PATTERNS.items():
        if pattern.search(content):
            found.append(edge_type)
    return found


class KnowledgeGraph:
    """Entity-relationship knowledge graph for semantic memory linking.

    Extends CausalGraph with:
    - Named entity nodes with types
    - Typed edges (USES, PREFERS, WORKS_ON, etc.)
    - Multi-hop traversal
    - Memory-to-entity linking
    """

    def __init__(self) -> None:
        # Entity store: name_lower → Entity
        self._entities: Dict[str, Entity] = {}
        # Edges: source_lower → [Edge]
        self._edges: Dict[str, List[Edge]] = {}
        # Reverse edges: target_lower → [Edge]
        self._reverse_edges: Dict[str, List[Edge]] = {}
        # Memory → entities mapping
        self._memory_entities: Dict[str, List[str]] = {}

    @property
    def num_entities(self) -> int:
        return len(self._entities)

    @property
    def num_edges(self) -> int:
        return sum(len(v) for v in self._edges.values())

    def add_entity(self, entity: Entity) -> Entity:
        """Add or merge an entity into the graph."""
        key = entity.name.lower()
        if key in self._entities:
            existing = self._entities[key]
            existing.mention_count += 1
            for mid in entity.memory_ids:
                if mid not in existing.memory_ids:
                    existing.memory_ids.append(mid)
            return existing
        self._entities[key] = entity
        return entity

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: EdgeType,
        memory_id: str = "",
        weight: float = 1.0,
    ) -> Edge:
        """Add a typed edge between two entities."""
        src_key = source.lower()
        tgt_key = target.lower()

        edge = Edge(
            source=src_key,
            target=tgt_key,
            edge_type=edge_type,
            weight=weight,
            memory_id=memory_id,
        )
        self._edges.setdefault(src_key, []).append(edge)
        self._reverse_edges.setdefault(tgt_key, []).append(edge)
        return edge

    def link_memory(
        self, memory_id: str, content: str, user_name: str = ""
    ) -> List[Entity]:
        """Extract entities from content and create graph links.

        Called automatically by engine.add(). Returns extracted entities.
        """
        entities = extract_entities(content)
        relationships = detect_relationships(content)

        if not entities:
            return []

        entity_names = []
        for ent in entities:
            ent.memory_ids.append(memory_id)
            self.add_entity(ent)
            entity_names.append(ent.name.lower())

        self._memory_entities[memory_id] = entity_names

        # Create edges based on detected relationships
        # If user name is known, link entities to user
        person_entities = [e for e in entities if e.type == EntityType.PERSON]
        other_entities = [e for e in entities if e.type != EntityType.PERSON]

        # Link person → technology/org/project edges
        for rel in relationships:
            persons = (
                person_entities
                if person_entities
                else (
                    [Entity(name=user_name, type=EntityType.PERSON)]
                    if user_name
                    else []
                )
            )
            for person in persons:
                for other in other_entities:
                    self.add_edge(person.name, other.name, rel, memory_id)

        # If no person but multiple entities, link them with RELATED_TO
        if not person_entities and len(other_entities) > 1:
            for i, e1 in enumerate(other_entities):
                for e2 in other_entities[i + 1 :]:
                    rel = relationships[0] if relationships else EdgeType.RELATED_TO
                    self.add_edge(e1.name, e2.name, rel, memory_id)

        return entities

    def get_entity(self, name: str) -> Optional[Entity]:
        """Look up an entity by name."""
        return self._entities.get(name.lower())

    def get_edges(self, entity_name: str) -> List[Edge]:
        """Get all outgoing edges from an entity."""
        key = entity_name.lower()
        forward = self._edges.get(key, [])
        backward = self._reverse_edges.get(key, [])
        return forward + backward

    def neighbours(self, entity_name: str) -> Set[str]:
        """Get all directly connected entity names."""
        key = entity_name.lower()
        result: Set[str] = set()
        for e in self._edges.get(key, []):
            result.add(e.target)
        for e in self._reverse_edges.get(key, []):
            result.add(e.source)
        return result

    def traverse(self, entity_name: str, depth: int = 2) -> List[str]:
        """Multi-hop breadth-first traversal from an entity.

        Returns all entity names reachable within `depth` hops.
        """
        visited: Set[str] = set()
        queue = [(entity_name.lower(), 0)]
        result: List[str] = []

        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            if d > 0:
                result.append(current)

            if d < depth:
                for neighbour in self.neighbours(current):
                    if neighbour not in visited:
                        queue.append((neighbour, d + 1))

        return result

    def get_related_memory_ids(self, entity_name: str, depth: int = 2) -> List[str]:
        """Get all memory IDs connected to an entity within depth hops."""
        related_entities = [entity_name.lower()] + self.traverse(entity_name, depth)
        memory_ids: List[str] = []
        seen: Set[str] = set()

        for ent_name in related_entities:
            entity = self._entities.get(ent_name)
            if entity:
                for mid in entity.memory_ids:
                    if mid not in seen:
                        memory_ids.append(mid)
                        seen.add(mid)

        return memory_ids

    def find_entities_in_query(self, query: str) -> List[Entity]:
        """Find entities mentioned in a query string."""
        return extract_entities(query)

    def all_entities(self) -> List[Entity]:
        """Return all entities in the graph."""
        return list(self._entities.values())

    def all_edges(self) -> List[Edge]:
        """Return all edges in the graph."""
        result = []
        for edges in self._edges.values():
            result.extend(edges)
        return result

    def to_dict(self) -> Dict:
        """Serialize the graph for inspection/debugging."""
        return {
            "entities": {
                k: {
                    "name": v.name,
                    "type": v.type.value,
                    "mentions": v.mention_count,
                    "memory_ids": v.memory_ids,
                }
                for k, v in self._entities.items()
            },
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "type": e.edge_type.value,
                    "memory_id": e.memory_id,
                }
                for edges in self._edges.values()
                for e in edges
            ],
            "stats": {
                "entities": self.num_entities,
                "edges": self.num_edges,
            },
        }

    def clear(self) -> None:
        self._entities.clear()
        self._edges.clear()
        self._reverse_edges.clear()
        self._memory_entities.clear()

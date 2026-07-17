"""Knowledge Graph — Entity Extraction & Semantic Linking.

Canonical graph substrate for OMem: nodes, relations, evidence, and provenance.
Memories are graph-backed units; vector search augments graph traversal.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from ...types import GraphNode, NodeKind, Provenance

logger = logging.getLogger(__name__)

try:
    import xxhash

    def _fast_hash(data: str) -> str:
        return xxhash.xxh64_hexdigest(data.encode("utf-8"))[:12]
except ImportError:
    import hashlib

    def _fast_hash(data: str) -> str:
        return hashlib.md5(data.encode("utf-8")).hexdigest()[:12]


class EntityType(Enum):
    """Types of entities extracted from memory content.

    Charter coverage: People, Projects, Systems, Documents, Incidents, Tasks
    (plus technology / organization / location / concept).
    """

    PERSON = "person"
    TECHNOLOGY = "technology"
    PROJECT = "project"
    ORGANIZATION = "organization"
    LOCATION = "location"
    CONCEPT = "concept"
    SYSTEM = "system"
    DOCUMENT = "document"
    INCIDENT = "incident"
    TASK = "task"


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
    ASSERTED = "asserted"


@dataclass
class Entity:
    """A named entity extracted from memory content."""

    name: str
    type: EntityType
    memory_ids: List[str] = field(default_factory=list)
    mention_count: int = 1
    node_id: str = ""

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

    source: str
    target: str
    edge_type: EdgeType
    weight: float = 1.0
    memory_id: str = ""
    label: str = ""
    id: str = ""
    evidence_count: int = 1
    confidence: float = 1.0
    provenance: Provenance = field(default_factory=Provenance)


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

_ORG_PATTERNS = re.compile(
    r"\b("
    r"Google|Microsoft|Apple|Amazon|Meta|Facebook|Netflix|Uber|Airbnb|"
    r"OpenAI|Anthropic|DeepMind|FICO|NVIDIA|Intel|AMD|IBM|Oracle|"
    r"Stripe|Shopify|Salesforce|Adobe|Twitter|X Corp|LinkedIn|"
    r"MIT|Stanford|Berkeley|Harvard|"
    r"(?:[A-Z][a-z]+ (?:Inc|Corp|Ltd|LLC|Co|Foundation|Labs?)\.?)"
    r")\b"
)

_PERSON_PATTERNS = [
    re.compile(
        r"(?:my name is|i am|i'm|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:told|asked|met|know|called)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),
]

_LOCATION_PATTERNS = re.compile(
    r"\b(?:in|at|from|to|near)\s+(" r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*" r")\b"
)

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
    """Extract named entities from memory content using regex patterns."""
    entities: List[Entity] = []
    seen: Set[str] = set()

    for pattern in _PERSON_PATTERNS:
        for match in pattern.finditer(content):
            name = match.group(1).strip()
            key = name.lower()
            if key not in seen and len(name) > 1:
                entities.append(Entity(name=name, type=EntityType.PERSON))
                seen.add(key)

    for match in _TECH_PATTERNS.finditer(content):
        name = match.group(1)
        key = name.lower()
        if key not in seen:
            entities.append(Entity(name=name, type=EntityType.TECHNOLOGY))
            seen.add(key)

    for match in _ORG_PATTERNS.finditer(content):
        name = match.group(1).strip()
        key = name.lower()
        if key not in seen and len(name) > 2:
            entities.append(Entity(name=name, type=EntityType.ORGANIZATION))
            seen.add(key)

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

    # Charter entity types: systems, documents, incidents, tasks, projects
    for pattern, etype in (
        (
            re.compile(
                r"\b((?:[A-Z][\w-]+(?:Service|API|Cluster|DB|Database|System|Gateway|Worker)))\b"
            ),
            EntityType.SYSTEM,
        ),
        (
            re.compile(
                r"\b((?:RFC|ADR|PR|DOC)[- ]?\d+|README(?:\.\w+)?|[A-Za-z0-9_-]+\.md)\b",
                re.IGNORECASE,
            ),
            EntityType.DOCUMENT,
        ),
        (
            re.compile(
                r"\b((?:INC|INCIDENT|OUTAGE)[- ]?\d+|incident\s+[A-Za-z0-9_-]+)\b",
                re.IGNORECASE,
            ),
            EntityType.INCIDENT,
        ),
        (
            re.compile(
                r"\b((?:TASK|TODO|TICKET|JIRA)[- ]?[A-Z0-9-]+)\b",
                re.IGNORECASE,
            ),
            EntityType.TASK,
        ),
        (
            re.compile(
                r"\b(?:project|repo(?:sitory)?)\s+([A-Za-z0-9_./-]+)\b",
                re.IGNORECASE,
            ),
            EntityType.PROJECT,
        ),
    ):
        for match in pattern.finditer(content):
            name = match.group(1).strip()
            key = f"{etype.value}:{name.lower()}"
            if key not in seen and len(name) > 1:
                entities.append(Entity(name=name, type=etype))
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
    """Entity-relationship knowledge graph — canonical memory substrate store."""

    def __init__(self) -> None:
        self._entities: Dict[str, Entity] = {}
        self._nodes: Dict[str, GraphNode] = {}
        self._label_to_node: Dict[str, str] = {}
        self._edges: Dict[str, List[Edge]] = {}
        self._reverse_edges: Dict[str, List[Edge]] = {}
        self._edge_index: Dict[str, Edge] = {}
        self._memory_entities: Dict[str, List[str]] = {}
        self._memory_node_ids: Dict[str, List[str]] = {}
        self._memory_edge_ids: Dict[str, List[str]] = {}

    @property
    def num_entities(self) -> int:
        return len(self._entities)

    @property
    def num_edges(self) -> int:
        return len(self._edge_index)

    def _node_id_for(self, label: str, entity_type: EntityType) -> str:
        return _fast_hash(f"node:{label.lower()}:{entity_type.value}")

    def _edge_id_for(self, source: str, target: str, edge_type: EdgeType) -> str:
        return _fast_hash(f"edge:{source.lower()}:{target.lower()}:{edge_type.value}")

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_node_by_label(self, label: str) -> Optional[GraphNode]:
        node_id = self._label_to_node.get(label.lower())
        return self._nodes.get(node_id) if node_id else None

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        return self._edge_index.get(edge_id)

    def add_entity(self, entity: Entity) -> Entity:
        """Add or merge an entity into the graph."""
        key = entity.name.lower()
        node_id = self._node_id_for(entity.name, entity.type)
        entity.node_id = node_id

        if key in self._entities:
            existing = self._entities[key]
            existing.mention_count += 1
            for mid in entity.memory_ids:
                if mid not in existing.memory_ids:
                    existing.memory_ids.append(mid)
            node = self._nodes.get(existing.node_id)
            if node:
                node.mention_count = existing.mention_count
                node.evidence_count += 1
                node.updated_at = time.time()
                for mid in entity.memory_ids:
                    if mid not in node.memory_ids:
                        node.memory_ids.append(mid)
            return existing

        self._entities[key] = entity
        node = GraphNode(
            id=node_id,
            label=entity.name,
            kind=NodeKind.ENTITY,
            entity_type=entity.type.value,
            memory_ids=list(entity.memory_ids),
            mention_count=entity.mention_count,
        )
        self._nodes[node_id] = node
        self._label_to_node[key] = node_id
        return entity

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: EdgeType,
        memory_id: str = "",
        weight: float = 1.0,
        confidence: float = 1.0,
        provenance: Optional[Provenance] = None,
    ) -> Edge:
        """Add or reinforce a typed edge between two entities."""
        src_key = source.lower()
        tgt_key = target.lower()
        edge_id = self._edge_id_for(source, target, edge_type)

        if edge_id in self._edge_index:
            existing = self._edge_index[edge_id]
            existing.weight = min(existing.weight + 0.1, 5.0)
            existing.evidence_count += 1
            existing.confidence = min(
                1.0, (existing.confidence + confidence) / 2.0 + 0.05
            )
            if memory_id and memory_id not in self._memory_edge_ids.setdefault(memory_id, []):
                self._memory_edge_ids[memory_id].append(edge_id)
            return existing

        edge = Edge(
            id=edge_id,
            source=src_key,
            target=tgt_key,
            edge_type=edge_type,
            weight=weight,
            memory_id=memory_id,
            confidence=confidence,
            provenance=provenance or Provenance(source="user", memory_id=memory_id),
        )
        self._edge_index[edge_id] = edge
        self._edges.setdefault(src_key, []).append(edge)
        self._reverse_edges.setdefault(tgt_key, []).append(edge)
        if memory_id:
            self._memory_edge_ids.setdefault(memory_id, []).append(edge_id)
        return edge

    def ingest_experience(
        self,
        memory_id: str,
        content: str,
        source: str = "user",
        confidence: float = 1.0,
        namespace: str = "default",
        user_name: str = "",
    ) -> Dict:
        """Graph-first ingestion: extract entities, relations, evidence, provenance."""
        entities = extract_entities(content)
        relationships = detect_relationships(content)
        node_ids: List[str] = []
        edge_ids: List[str] = []
        entity_names: List[str] = []

        if not entities:
            return {
                "node_ids": [],
                "edge_ids": [],
                "entities": [],
                "confidence": confidence,
                "evidence_count": 1,
                "relation_types": [r.value for r in relationships],
            }

        for ent in entities:
            ent.memory_ids.append(memory_id)
            merged = self.add_entity(ent)
            entity_names.append(merged.name)
            if merged.node_id:
                node_ids.append(merged.node_id)
                self._memory_node_ids.setdefault(memory_id, []).append(merged.node_id)

        self._memory_entities[memory_id] = [n.lower() for n in entity_names]

        person_entities = [e for e in entities if e.type == EntityType.PERSON]
        other_entities = [e for e in entities if e.type != EntityType.PERSON]
        prov = Provenance(
            source=source, memory_id=memory_id, namespace=namespace
        )

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
                    edge = self.add_edge(
                        person.name,
                        other.name,
                        rel,
                        memory_id=memory_id,
                        confidence=confidence,
                        provenance=prov,
                    )
                    edge_ids.append(edge.id)

        if not person_entities and len(other_entities) > 1:
            rel = relationships[0] if relationships else EdgeType.RELATED_TO
            for i, e1 in enumerate(other_entities):
                for e2 in other_entities[i + 1 :]:
                    edge = self.add_edge(
                        e1.name,
                        e2.name,
                        rel,
                        memory_id=memory_id,
                        confidence=confidence,
                        provenance=prov,
                    )
                    edge_ids.append(edge.id)

        return {
            "node_ids": list(dict.fromkeys(node_ids)),
            "edge_ids": list(dict.fromkeys(edge_ids)),
            "entities": entity_names,
            "confidence": confidence,
            "evidence_count": max(len(edge_ids), 1),
            "relation_types": [r.value for r in relationships],
        }

    def link_memory(
        self, memory_id: str, content: str, user_name: str = ""
    ) -> List[Entity]:
        """Backward-compatible wrapper around graph-first ingestion."""
        payload = self.ingest_experience(
            memory_id=memory_id,
            content=content,
            user_name=user_name,
        )
        return [
            self._entities[name.lower()]
            for name in payload.get("entities", [])
            if name.lower() in self._entities
        ]

    def link_entities(
        self,
        source: str,
        target: str,
        edge_type: EdgeType = EdgeType.RELATED_TO,
        memory_id: str = "",
        weight: float = 1.0,
        confidence: float = 1.0,
    ) -> str:
        """Explicitly link two entities with a typed relation."""
        self.add_entity(Entity(name=source, type=EntityType.CONCEPT))
        self.add_entity(Entity(name=target, type=EntityType.CONCEPT))
        edge = self.add_edge(
            source,
            target,
            edge_type,
            memory_id=memory_id,
            weight=weight,
            confidence=confidence,
        )
        return edge.id

    def assert_fact(
        self,
        subject: str,
        relation: EdgeType,
        obj: str,
        memory_id: str,
        confidence: float = 0.9,
        source: str = "assertion",
    ) -> Dict[str, str]:
        """Assert a structured fact as a high-confidence graph relation."""
        self.add_entity(Entity(name=subject, type=EntityType.CONCEPT))
        self.add_entity(Entity(name=obj, type=EntityType.CONCEPT))
        edge = self.add_edge(
            subject,
            obj,
            relation,
            memory_id=memory_id,
            weight=2.0,
            confidence=confidence,
            provenance=Provenance(source=source, memory_id=memory_id),
        )
        subj_node = self.get_node_by_label(subject)
        obj_node = self.get_node_by_label(obj)
        return {
            "edge_id": edge.id,
            "subject_node_id": subj_node.id if subj_node else "",
            "object_node_id": obj_node.id if obj_node else "",
        }

    def create_insight_node(
        self,
        label: str,
        memory_ids: List[str],
        themes: Optional[List[str]] = None,
        confidence: float = 0.85,
    ) -> GraphNode:
        """Create an abstract insight node during consolidation."""
        node_id = _fast_hash(f"insight:{label.lower()}:{time.time()}")
        node = GraphNode(
            id=node_id,
            label=label[:120],
            kind=NodeKind.INSIGHT,
            entity_type="insight",
            memory_ids=list(memory_ids),
            mention_count=len(memory_ids),
            confidence=confidence,
            evidence_count=len(memory_ids),
        )
        self._nodes[node_id] = node
        self._label_to_node[label.lower()] = node_id

        insight_entity = Entity(
            name=label[:120],
            type=EntityType.CONCEPT,
            memory_ids=list(memory_ids),
            node_id=node_id,
        )
        self._entities[label.lower()] = insight_entity

        if themes:
            for theme in themes[:5]:
                theme_entity = Entity(name=theme, type=EntityType.CONCEPT)
                self.add_entity(theme_entity)
                self.add_edge(
                    label,
                    theme,
                    EdgeType.RELATED_TO,
                    memory_id=memory_ids[0] if memory_ids else "",
                    confidence=confidence,
                )
        return node

    def graph_score_for_memory(
        self,
        memory_id: str,
        query_entity_names: List[str],
        depth: int = 2,
    ) -> float:
        """Score graph proximity between a memory and query entities."""
        mem_entities = self._memory_entities.get(memory_id, [])
        if not mem_entities or not query_entity_names:
            return 0.0

        best = 0.0
        query_keys = {n.lower() for n in query_entity_names}
        for mem_ent in mem_entities:
            if mem_ent in query_keys:
                return 1.0
            reachable = set(self.traverse(mem_ent, depth=depth))
            overlap = query_keys.intersection(reachable)
            if overlap:
                best = max(best, len(overlap) / max(len(query_keys), 1))
        return min(best, 1.0)

    def entity_centrality(self, entity_name: str) -> float:
        """Normalized degree centrality for an entity [0, 1]."""
        key = entity_name.lower()
        degree = len(self._edges.get(key, [])) + len(self._reverse_edges.get(key, []))
        if degree == 0:
            return 0.0
        max_degree = max(
            (
                len(self._edges.get(k, [])) + len(self._reverse_edges.get(k, []))
                for k in self._entities
            ),
            default=1,
        )
        return min(degree / max(max_degree, 1), 1.0)

    def centrality_for_memory(
        self,
        memory_id: str,
        query_entity_names: Optional[List[str]] = None,
    ) -> float:
        """Average centrality of entities linked to a memory, boosted by query overlap."""
        entities = self._memory_entities.get(memory_id, [])
        if not entities:
            return 0.0
        scores = [self.entity_centrality(e) for e in entities]
        base = sum(scores) / len(scores)
        if not query_entity_names:
            return base
        query_keys = {n.lower() for n in query_entity_names}
        if any(e in query_keys for e in entities):
            return min(base + 0.2, 1.0)
        return base

    def query(self, entity_name: str, depth: int = 2) -> List[str]:
        """Return memory IDs related to an entity within depth hops."""
        return self.get_related_memory_ids(entity_name, depth=depth)

    def get_entity(self, name: str) -> Optional[Entity]:
        return self._entities.get(name.lower())

    def get_edges(self, entity_name: str) -> List[Edge]:
        key = entity_name.lower()
        forward = self._edges.get(key, [])
        backward = self._reverse_edges.get(key, [])
        return forward + backward

    def neighbours(self, entity_name: str) -> Set[str]:
        key = entity_name.lower()
        result: Set[str] = set()
        for e in self._edges.get(key, []):
            result.add(e.target)
        for e in self._reverse_edges.get(key, []):
            result.add(e.source)
        return result

    def traverse(self, entity_name: str, depth: int = 2) -> List[str]:
        """BFS entity traversal; uses Rust ``graph_bfs_batch`` when available."""
        seed = entity_name.lower()
        # Prefer Rust parallel BFS over adjacency list
        try:
            import omem_rust

            if hasattr(omem_rust, "graph_bfs_batch"):
                labels = list(self._entities.keys())
                if not labels:
                    return []
                index = {lab: i for i, lab in enumerate(labels)}
                if seed not in index:
                    return []
                adj: List[List[int]] = [[] for _ in labels]
                for src, edges in self._edges.items():
                    if src not in index:
                        continue
                    si = index[src]
                    for e in edges:
                        tgt = e.target.lower() if hasattr(e, "target") else str(e.target).lower()
                        if tgt in index:
                            adj[si].append(index[tgt])
                for src, edges in self._reverse_edges.items():
                    if src not in index:
                        continue
                    si = index[src]
                    for e in edges:
                        tgt = e.source.lower() if hasattr(e, "source") else str(e.source).lower()
                        if tgt in index:
                            adj[si].append(index[tgt])
                found = omem_rust.graph_bfs_batch(adj, [index[seed]], depth, 64)
                if found:
                    return [labels[i] for i in found[0] if i < len(labels)]
        except Exception:
            pass

        visited: Set[str] = set()
        queue = [(seed, 0)]
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
        return extract_entities(query)

    def all_entities(self) -> List[Entity]:
        return list(self._entities.values())

    def all_nodes(self) -> List[GraphNode]:
        return list(self._nodes.values())

    def all_edges(self) -> List[Edge]:
        return list(self._edge_index.values())

    def persist_edges(
        self,
        backend,
        namespace: str = "default",
    ) -> int:
        """Flush graph edges to a durable backend (Postgres ``save_edge``).

        Returns number of edges written. No-op if backend lacks ``save_edge``.
        """
        if backend is None or not hasattr(backend, "save_edge"):
            return 0
        written = 0
        for edge in self.all_edges():
            try:
                backend.save_edge(
                    namespace=namespace,
                    source_id=edge.source,
                    target_id=edge.target,
                    relation_type=edge.edge_type.value
                    if hasattr(edge.edge_type, "value")
                    else str(edge.edge_type),
                    confidence=float(edge.confidence),
                )
                written += 1
            except Exception as exc:
                logger.warning("edge persist failed: %s", exc)
        return written

    def to_dict(self) -> Dict:
        return {
            "entities": {
                k: {
                    "name": v.name,
                    "type": v.type.value,
                    "mentions": v.mention_count,
                    "memory_ids": v.memory_ids,
                    "node_id": v.node_id,
                }
                for k, v in self._entities.items()
            },
            "nodes": {
                nid: {
                    "label": n.label,
                    "kind": n.kind.value,
                    "confidence": n.confidence,
                    "evidence_count": n.evidence_count,
                }
                for nid, n in self._nodes.items()
            },
            "edges": [
                {
                    "id": e.id,
                    "source": e.source,
                    "target": e.target,
                    "type": e.edge_type.value,
                    "memory_id": e.memory_id,
                    "confidence": e.confidence,
                    "evidence_count": e.evidence_count,
                }
                for e in self._edge_index.values()
            ],
            "stats": {
                "entities": self.num_entities,
                "nodes": len(self._nodes),
                "edges": self.num_edges,
            },
        }

    def clear(self) -> None:
        self._entities.clear()
        self._nodes.clear()
        self._label_to_node.clear()
        self._edges.clear()
        self._reverse_edges.clear()
        self._edge_index.clear()
        self._memory_entities.clear()
        self._memory_node_ids.clear()
        self._memory_edge_ids.clear()

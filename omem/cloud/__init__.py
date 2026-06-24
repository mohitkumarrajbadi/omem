"""V2 cloud layer — Cloud Phases C1–C5 of the implementation plan.

Purpose: HTTP client and remote backend that makes the same SDK work
locally (SQLite) or against Akamai Agent State Cloud (Linode).

Components (implemented in Cloud Phases C1–C5):
    CloudBackend   — Backend adapter that routes calls over HTTP
    OMemCloudClient — Low-level REST client
    server         — FastAPI app (deploy/docker/Dockerfile.cloud)

Environment contract (cloud mode):
    OMEM_ENDPOINT  — https://state.akamai.ai
    OMEM_API_KEY   — omem_sk_...
    OMEM_ORG       — org name / ID

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Cloud Phases C1–C5
     docs/roadmap/AKAMAI_LINODE_DEPLOYMENT.md
"""

__all__: list = []

# Governance

OMem is a maintainer-led open source project. The project optimizes for local-first AI infrastructure, stable public APIs, practical agent integrations, and a contributor experience that is welcoming without being loose about quality.

## Decision Making

Maintainers make final calls on API stability, release timing, roadmap scope, and security decisions. Contributors are encouraged to open design discussions before large changes.

For major v2 work, prefer an issue or discussion first when the change:

- Adds or changes public API
- Introduces a new backend or integration
- Changes retrieval scoring behavior
- Alters persistence formats
- Changes security, encryption, deletion, or retention behavior

## Review Standards

A PR should be mergeable when it:

- Solves one clear problem
- Includes tests for changed behavior
- Preserves the stable `OMem` API unless a migration is documented
- Keeps the base install local-first and zero-config
- Avoids external API calls in tests
- Updates docs/examples for user-facing changes

## Release Channels

| Branch | Purpose |
|---|---|
| `main` | Stable OSS releases |
| `dev` | Active development |
| `staging` | Pre-release integration testing |
| `cloud` | Akamai/Linode tech-preview demo (deployable proof) |

Patch releases should be boring. Minor releases may add APIs. Breaking changes require a migration guide.

**Cloud proof:** merge `staging` → `cloud`, deploy with `./deploy/scripts/cloud-proof-deploy.sh`. See [docs/guides/CLOUD_PROOF.md](./docs/guides/CLOUD_PROOF.md).

## Security

Security issues should follow [SECURITY.md](./SECURITY.md). Do not open public issues for suspected vulnerabilities.

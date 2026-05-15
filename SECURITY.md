# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.8.x   | :white_check_mark: |
| < 0.8   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue in OMem, please report it responsibly.

### How to Report

**Do not** open a public GitHub issue for security vulnerabilities.

Instead, please report security issues by emailing the maintainers directly:

**Email:** mohitkumarrajbadi@gmail.com

Include the following information in your report:

1. **Description**: A clear description of the vulnerability
2. **Impact**: The potential impact and severity of the issue
3. **Reproduction**: Step-by-step instructions to reproduce the vulnerability
4. **Environment**: Version of OMem, Python version, operating system
5. **Proof of Concept**: If applicable, code or configuration demonstrating the issue
6. **Suggested Fix**: If you have ideas for how to address the vulnerability

### What to Expect

- **Acknowledgment**: We will acknowledge receipt of your report within 48 hours
- **Updates**: We will provide regular updates on our progress (at least every 7 days)
- **Timeline**: We aim to patch critical vulnerabilities within 7 days
- **Credit**: We will publicly credit you for responsible disclosure (unless you prefer to remain anonymous)
- **CVE**: For significant vulnerabilities, we will request a CVE identifier

### Security Best Practices

When using OMem in production:

1. **Data Protection**
   - Never store unencrypted sensitive data in memories
   - Use namespace isolation for multi-tenant deployments
   - Regularly audit stored memories for sensitive content

2. **Access Control**
   - Restrict file system permissions on database files (chmod 600 recommended)
   - Use appropriate OS-level access controls for the ~/.omem directory
   - Implement authentication if exposing OMem via network services

3. **Input Validation**
   - Validate and sanitize all user inputs before storing as memories
   - Be cautious with memories containing executable code or SQL queries
   - Use parameterized queries when interfacing with external systems

4. **Network Security**
   - If running the MCP server, use TLS/SSL in production
   - Bind the server to localhost unless remote access is required
   - Implement rate limiting to prevent abuse

5. **Dependencies**
   - Keep OMem and its dependencies up to date
   - Monitor security advisories for sentence-transformers, FAISS, and other dependencies
   - Run `pip audit` or similar tools to detect vulnerable dependencies

6. **Monitoring**
   - Enable structured logging to detect suspicious activity
   - Monitor for unusual query patterns or memory access
   - Set up alerts for failed authentication attempts or quota violations

## Known Security Considerations

### Thread Safety

OMem uses SQLite with `check_same_thread=False`. While we implement connection pooling, ensure you understand the concurrency model before using OMem in highly concurrent environments.

### Secret Detection

OMem includes basic secret detection to prevent accidental storage of API keys and credentials. However, this is a best-effort mechanism and should not be relied upon as the sole protection against credential leakage.

### Local Storage

By default, OMem stores all data unencrypted in a local SQLite database. If your memories contain sensitive information, implement encryption at rest using OS-level tools like:
- Linux: LUKS, dm-crypt
- macOS: FileVault
- Windows: BitLocker

## Security Updates

We will announce security updates through:

1. GitHub Security Advisories
2. Release notes in CHANGELOG.md
3. Git tags with security patches

Subscribe to GitHub notifications for this repository to stay informed.

## Scope

This security policy applies to:

- The OMem core library (Python package)
- Official CLI tools
- MCP server implementation
- Documentation and example code

Third-party integrations and plugins are outside the scope of this policy.

## Acknowledgments

We appreciate the security research community's efforts in keeping OMem safe. Responsible disclosures will be acknowledged in our release notes and security advisories.

Thank you for helping keep OMem and its users secure.

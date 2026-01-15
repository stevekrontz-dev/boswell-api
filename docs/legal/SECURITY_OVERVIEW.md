# Security Overview

*Last updated: January 15, 2026*

Security isn't a feature - it's foundational. Here's how we protect your data.

## Encryption

### At Rest

All memories stored in Boswell are encrypted using **AES-256-GCM** encryption. This is the same standard used by banks and government agencies.

We use **per-tenant key isolation**, meaning each customer's data is encrypted with a unique key. Even if an attacker gained access to our database, they couldn't read your memories without your specific encryption key.

### In Transit

All data transmitted between:
- Your device and our servers
- Our servers and third-party services (Stripe, OpenAI, Anthropic)
- Internal service communication

...uses **TLS 1.3** encryption.

### Key Management

Encryption keys are managed through **AWS Key Management Service (KMS)**. Keys are:
- Generated securely by AWS
- Never stored in plaintext
- Rotated according to best practices
- Access-logged for audit purposes

## Infrastructure

### Hosting

Boswell runs on **Railway**, a modern cloud platform. Our infrastructure includes:

- Isolated containers for each service
- Automatic scaling under load
- Geographic redundancy
- Regular security patches

### Database

We use **PostgreSQL** with:
- Encrypted storage volumes
- Automated backups
- Point-in-time recovery capability
- Connection encryption required

## Access Controls

### Internal Access

- Only essential personnel have production access
- Access requires multi-factor authentication
- All access is logged and audited
- We follow the principle of least privilege

### Your Access

- Passwords are hashed using bcrypt
- API keys use SHA-256 hashing
- Session tokens expire after inactivity
- You can revoke API keys at any time

## Data Handling

### What We Store

- Your memories (encrypted)
- Vector embeddings (for search)
- Account information
- Usage metadata

### What We Don't Store

- Full conversation transcripts
- Credit card numbers (Stripe handles this)
- Passwords in plaintext

### Data Retention

- Active accounts: Data retained indefinitely
- After cancellation: 30 days active, then deleted
- Backups: Purged within 60 days of cancellation

## Third-Party Security

We carefully vet our subprocessors:

| Service | Purpose | Security |
|---------|---------|----------|
| **Railway** | Hosting | SOC 2 Type II |
| **Stripe** | Payments | PCI DSS Level 1 |
| **OpenAI** | Embeddings | Enterprise security |
| **Anthropic** | AI | Enterprise security |
| **AWS KMS** | Key management | FIPS 140-2 |

## Incident Response

If we discover a security incident:

1. We contain and investigate immediately
2. We notify affected users within 72 hours
3. We provide clear information about what happened
4. We take steps to prevent recurrence

## Reporting Security Issues

Found a vulnerability? Please report it to security@askboswell.com.

We appreciate responsible disclosure and will:
- Acknowledge receipt within 24 hours
- Keep you informed of our investigation
- Credit you (if desired) when we fix the issue

Please do not publicly disclose issues until we've had time to address them.

## Compliance

### HECVAT

We maintain documentation for the Higher Education Community Vendor Assessment Toolkit (HECVAT), making Boswell suitable for university deployments.

### CCPA / GDPR

We comply with California Consumer Privacy Act and EU General Data Protection Regulation requirements. See our Privacy Policy for details.

## Questions

Security questions? Contact security@askboswell.com.

---

*Adapted from the Basecamp open-source policies / CC BY 4.0*

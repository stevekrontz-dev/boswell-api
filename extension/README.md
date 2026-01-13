# Boswell Desktop Extension

This directory contains the MCPB (MCP Bundle) extension builder for Boswell SaaS.

## Overview

The extension builder generates personalized `.mcpb` files that users can download from the dashboard and install in Claude Desktop with a single double-click.

## Directory Structure

```
extension/
├── README.md           # This file
├── builder/            # Extension builder CLI and library
│   ├── __init__.py
│   ├── cli.py          # CLI entrypoint
│   └── bundler.py      # Bundle generation logic
├── templates/          # Template files for bundle generation
│   └── manifest.template.json
└── server/             # MCP server code to be bundled
    └── (Node.js server files)
```

## Architecture

### Bundle Generation Flow

1. User logs into dashboard
2. User clicks "Download Extension"
3. Backend generates personalized `.mcpb`:
   - Injects user's `tenant_id` and `api_key` into `user_config`
   - Bundles pre-compiled MCP server with dependencies
   - Creates ZIP archive with manifest.json
4. User downloads and double-clicks to install
5. Claude Desktop prompts for any required config
6. Extension auto-connects to Boswell API

### MCPB Format (v0.3)

Per the [MCP Bundle specification](https://github.com/modelcontextprotocol/mcpb):

- `.mcpb` files are ZIP archives
- Must contain `manifest.json` at root
- Server type: `node` (recommended for zero-friction install)
- User configuration via `user_config` schema

### Key Dependencies

- **W1P3 (API Key Management)**: Required before W4P2 implementation
  - Need API key generation/validation endpoints
  - Need secure key injection into bundles

## Status

- [x] W4P1: Research & Spec (Complete - see Boswell commit f373cfab)
- [ ] W4P2: Extension Builder (Blocked on W1P3)
- [ ] W4P3: Dashboard Integration

## Owner

CC4 - Desktop Extension domain

# Boswell MCP Server (Extension Bundle)

This directory will contain the Node.js MCP server code that gets bundled into the `.mcpb` extension.

## Why Node.js?

Per MCPB spec recommendations:
- Node.js ships with Claude Desktop (macOS & Windows)
- Zero additional runtime installation required for users
- Reduces friction vs Python which requires user to have Python installed

## Structure (W4P2)

```
server/
├── index.js          # Main entry point
├── package.json      # Dependencies (bundled in node_modules/)
├── node_modules/     # Pre-bundled dependencies
└── lib/
    ├── client.js     # Boswell API client
    ├── tools.js      # MCP tool implementations
    └── transport.js  # stdio transport handler
```

## Implementation Notes

The server will:
1. Read credentials from environment variables (injected by Claude Desktop from user_config)
2. Connect to Boswell API at the configured endpoint
3. Expose MCP tools matching the existing Python implementation
4. Use stdio transport per MCP protocol

## Dependencies

Minimal dependencies for small bundle size:
- `@modelcontextprotocol/sdk` - MCP server SDK
- `node-fetch` or built-in fetch - API calls

## Port from Python

The existing Python MCP server is in `/c/dev/infrastructure/boswell-mcp-repo/`:
- `app.py` - Main server implementation
- `server.py` - MCP protocol handler

W4P2 will port these to Node.js for the extension bundle.

## Blocked On

- W1P3: API Key Management (need key validation endpoints)
- W4P1: Research complete (f373cfab)

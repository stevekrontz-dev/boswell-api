#!/usr/bin/env node
/**
 * Boswell MCP Server - Node.js Edition
 *
 * Gives Claude Desktop direct access to Boswell memory system.
 * Exposes 13 tools that proxy to the Boswell API.
 *
 * Environment variables (injected by Claude Desktop from user_config):
 *   BOSWELL_API_KEY - User's API key for authentication
 *   BOSWELL_TENANT_ID - User's tenant identifier
 *   BOSWELL_API_ENDPOINT - Boswell API URL (default: production)
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

// Configuration from environment
const API_ENDPOINT = process.env.BOSWELL_API_ENDPOINT || 'https://boswell-api-production.up.railway.app';
const API_KEY = process.env.BOSWELL_API_KEY || '';
const TENANT_ID = process.env.BOSWELL_TENANT_ID || '';

/**
 * Make an authenticated request to the Boswell API
 */
async function boswellRequest(method, path, params = {}, body = null) {
  const url = new URL(`${API_ENDPOINT}${path}`);

  // Add query params for GET requests
  if (method === 'GET' && Object.keys(params).length > 0) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  const headers = {
    'Content-Type': 'application/json',
  };

  // Add auth header if API key is configured
  if (API_KEY) {
    headers['Authorization'] = `Bearer ${API_KEY}`;
  }

  const options = {
    method,
    headers,
  };

  if (body && method !== 'GET') {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url.toString(), options);
    const data = await response.json();

    if (!response.ok) {
      return { error: `HTTP ${response.status}`, details: data };
    }

    return data;
  } catch (error) {
    return { error: 'Request failed', details: error.message };
  }
}

// Tool definitions matching the Python MCP server
const TOOLS = [
  {
    name: 'boswell_startup',
    description: 'Load startup context in ONE call. Returns sacred_manifest (active commitments) + tool_registry (available tools). Call this FIRST at the start of every conversation.',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'boswell_brief',
    description: 'Get a quick context brief of current Boswell state - recent commits, pending sessions, all branches. Use this at conversation start to understand what\'s been happening.',
    inputSchema: {
      type: 'object',
      properties: {
        branch: {
          type: 'string',
          description: 'Branch to focus on (default: command-center)',
          default: 'command-center',
        },
      },
    },
  },
  {
    name: 'boswell_branches',
    description: 'List all cognitive branches in Boswell. Branches are: tint-atlanta (CRM/business), iris (research/BCI), tint-empire (franchise), family (personal), command-center (infrastructure), boswell (memory system).',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'boswell_head',
    description: 'Get the current HEAD commit for a specific branch.',
    inputSchema: {
      type: 'object',
      properties: {
        branch: {
          type: 'string',
          description: 'Branch name',
        },
      },
      required: ['branch'],
    },
  },
  {
    name: 'boswell_log',
    description: 'Get commit history for a branch. Shows what memories have been recorded.',
    inputSchema: {
      type: 'object',
      properties: {
        branch: {
          type: 'string',
          description: 'Branch name',
        },
        limit: {
          type: 'integer',
          description: 'Max commits (default: 10)',
          default: 10,
        },
      },
      required: ['branch'],
    },
  },
  {
    name: 'boswell_search',
    description: 'Search memories across all branches by keyword. Returns matching content with commit info.',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query',
        },
        branch: {
          type: 'string',
          description: 'Optional: limit to branch',
        },
        limit: {
          type: 'integer',
          description: 'Max results (default: 10)',
          default: 10,
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'boswell_recall',
    description: 'Recall a specific memory by its blob hash or commit hash.',
    inputSchema: {
      type: 'object',
      properties: {
        hash: {
          type: 'string',
          description: 'Blob hash',
        },
        commit: {
          type: 'string',
          description: 'Or commit hash',
        },
      },
    },
  },
  {
    name: 'boswell_links',
    description: 'List resonance links between memories. Shows cross-branch connections.',
    inputSchema: {
      type: 'object',
      properties: {
        branch: {
          type: 'string',
          description: 'Optional: filter by branch',
        },
        link_type: {
          type: 'string',
          description: 'Optional: resonance, causal, etc.',
        },
      },
    },
  },
  {
    name: 'boswell_graph',
    description: 'Get the full memory graph - all nodes and edges.',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'boswell_reflect',
    description: 'Get AI-surfaced insights - highly connected memories and patterns.',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'boswell_commit',
    description: 'Commit a new memory to Boswell. Preserves important decisions and context.',
    inputSchema: {
      type: 'object',
      properties: {
        branch: {
          type: 'string',
          description: 'Branch to commit to',
        },
        content: {
          type: 'object',
          description: 'Memory content as JSON',
        },
        message: {
          type: 'string',
          description: 'Commit message',
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'Optional tags',
        },
      },
      required: ['branch', 'content', 'message'],
    },
  },
  {
    name: 'boswell_link',
    description: 'Create a resonance link between two memories across branches.',
    inputSchema: {
      type: 'object',
      properties: {
        source_blob: { type: 'string' },
        target_blob: { type: 'string' },
        source_branch: { type: 'string' },
        target_branch: { type: 'string' },
        link_type: { type: 'string', default: 'resonance' },
        reasoning: { type: 'string', description: 'Why connected' },
      },
      required: ['source_blob', 'target_blob', 'source_branch', 'target_branch', 'reasoning'],
    },
  },
  {
    name: 'boswell_checkout',
    description: 'Switch focus to a different cognitive branch.',
    inputSchema: {
      type: 'object',
      properties: {
        branch: {
          type: 'string',
          description: 'Branch to check out',
        },
      },
      required: ['branch'],
    },
  },
];

/**
 * Handle tool calls by proxying to Boswell API
 */
async function handleToolCall(name, args) {
  switch (name) {
    case 'boswell_startup': {
      // Fetch sacred_manifest and tool_registry
      const startupData = { sacred_manifest: null, tool_registry: null };

      // Search for sacred_manifest
      const manifestResults = await boswellRequest('GET', '/v2/search', { q: 'sacred_manifest', limit: 5 });
      if (manifestResults.results) {
        for (const result of manifestResults.results) {
          if (result.blob_hash) {
            const recall = await boswellRequest('GET', '/v2/recall', { hash: result.blob_hash });
            try {
              const content = JSON.parse(recall.content || '{}');
              if (content.type === 'sacred_manifest') {
                startupData.sacred_manifest = content;
                break;
              }
            } catch {}
          }
        }
      }

      // Search for tool_registry
      const registryResults = await boswellRequest('GET', '/v2/search', { q: 'tool_registry', limit: 5 });
      if (registryResults.results) {
        for (const result of registryResults.results) {
          if (result.blob_hash) {
            const recall = await boswellRequest('GET', '/v2/recall', { hash: result.blob_hash });
            try {
              const content = JSON.parse(recall.content || '{}');
              if (content.type === 'tool_registry') {
                startupData.tool_registry = content;
                break;
              }
            } catch {}
          }
        }
      }

      return startupData;
    }

    case 'boswell_brief':
      return boswellRequest('GET', '/v2/quick-brief', { branch: args.branch || 'command-center' });

    case 'boswell_branches':
      return boswellRequest('GET', '/v2/branches');

    case 'boswell_head':
      return boswellRequest('GET', '/v2/head', { branch: args.branch });

    case 'boswell_log':
      return boswellRequest('GET', '/v2/log', { branch: args.branch, limit: args.limit || 10 });

    case 'boswell_search':
      return boswellRequest('GET', '/v2/search', {
        q: args.query,
        branch: args.branch,
        limit: args.limit || 10,
      });

    case 'boswell_recall':
      return boswellRequest('GET', '/v2/recall', {
        hash: args.hash,
        commit: args.commit,
      });

    case 'boswell_links':
      return boswellRequest('GET', '/v2/links', {
        branch: args.branch,
        link_type: args.link_type,
      });

    case 'boswell_graph':
      return boswellRequest('GET', '/v2/graph');

    case 'boswell_reflect':
      return boswellRequest('GET', '/v2/reflect');

    case 'boswell_commit':
      return boswellRequest('POST', '/v2/commit', {}, {
        branch: args.branch,
        content: args.content,
        message: args.message,
        author: 'claude-desktop',
        type: 'memory',
        tags: args.tags || [],
      });

    case 'boswell_link':
      return boswellRequest('POST', '/v2/link', {}, {
        source_blob: args.source_blob,
        target_blob: args.target_blob,
        source_branch: args.source_branch,
        target_branch: args.target_branch,
        link_type: args.link_type || 'resonance',
        reasoning: args.reasoning,
        created_by: 'claude-desktop',
      });

    case 'boswell_checkout':
      return boswellRequest('POST', '/v2/checkout', {}, { branch: args.branch });

    default:
      return { error: `Unknown tool: ${name}` };
  }
}

// Create the MCP server
const server = new Server(
  {
    name: 'boswell-mcp',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Register tool list handler
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: TOOLS };
});

// Register tool call handler
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    const result = await handleToolCall(name, args || {});
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({ error: error.message }),
        },
      ],
      isError: true,
    };
  }
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('Boswell MCP Server running on stdio');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});

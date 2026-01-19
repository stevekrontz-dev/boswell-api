#!/usr/bin/env python3
"""Add fingerprint MCP tool to app.py"""

# Read app.py
with open('app.py', 'r') as f:
    content = f.read()

# Find and replace the closing of MCP_TOOLS
old = '''        }
    },
]

def mcp_error_response'''

new = '''        }
    },
    # Branch Fingerprint Tools
    {
        "name": "boswell_validate_routing",
        "description": "Check which branch best matches content before committing. Returns suggested branch and confidence scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "object", "description": "Content to analyze"},
                "branch": {"type": "string", "description": "Requested branch"}
            },
            "required": ["content"]
        }
    },
]

def mcp_error_response'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Added boswell_validate_routing MCP tool')

# ============================================================
# MCP Streamable HTTP Handler
# ============================================================
# Implements MCP JSON-RPC 2.0 over HTTP POST
# Replaces the deprecated SSE-based boswell-mcp service
# Direct in-process routing - no HTTP round-trip

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "boswell-mcp"
MCP_SERVER_VERSION = "3.0.0"

def invoke_view(view_fn, method='GET', path='/', query_string=None, json_data=None, view_args=None):
    """
    Call Flask view function in synthetic request context.
    Returns (data_dict, status_code).
    
    view_args: dict of URL path parameters (e.g., {'task_id': '...'})
    """
    ctx_kwargs = {'method': method, 'path': path}
    if query_string:
        ctx_kwargs['query_string'] = query_string
    if json_data is not None:
        ctx_kwargs['json'] = json_data
        ctx_kwargs['content_type'] = 'application/json'
    
    with app.test_request_context(**ctx_kwargs):
        try:
            if view_args:
                result = view_fn(**view_args)
            else:
                result = view_fn()
            
            # Handle tuple returns (response, status_code)
            if isinstance(result, tuple):
                resp, code = result[0], result[1]
                if hasattr(resp, 'get_json'):
                    return resp.get_json(), code
                return resp, code
            # Handle Response objects
            if hasattr(result, 'get_json'):
                return result.get_json(), 200
            # Handle raw dicts (shouldn't happen but safety)
            return result, 200
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'error': str(e)}, 500


# Tool definitions - inline for single-service deployment
MCP_TOOLS = [
    {
        "name": "boswell_brief",
        "description": "Get a quick context brief of current Boswell state - recent commits, pending sessions, all branches. Use this at conversation start to understand what's been happening.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to focus on (default: command-center)", "default": "command-center"}
            }
        }
    },
    {
        "name": "boswell_branches",
        "description": "List all cognitive branches in Boswell. Branches are: tint-atlanta (CRM/business), iris (research/BCI), tint-empire (franchise), family (personal), command-center (infrastructure), boswell (memory system).",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_head",
        "description": "Get the current HEAD commit for a specific branch.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch name"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_log",
        "description": "Get commit history for a branch. Shows what memories have been recorded.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch name"},
                "limit": {"type": "integer", "description": "Max commits to return (default: 10)", "default": 10}
            },
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_search",
        "description": "Search memories across all branches by keyword. Returns matching content with commit info.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "branch": {"type": "string", "description": "Optional: limit search to specific branch"},
                "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "boswell_semantic_search",
        "description": "Semantic search using AI embeddings. Finds conceptually related memories even without exact keyword matches. Use for conceptual queries like 'decisions about architecture' or 'patent opportunities'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Conceptual search query"},
                "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "boswell_recall",
        "description": "Recall a specific memory by its blob hash or commit hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash": {"type": "string", "description": "Blob hash to recall"},
                "commit": {"type": "string", "description": "Or commit hash to recall"}
            }
        }
    },
    {
        "name": "boswell_links",
        "description": "List resonance links between memories. Shows cross-branch connections.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Optional: filter by branch"},
                "link_type": {"type": "string", "description": "Optional: filter by type (resonance, causal, contradiction, elaboration, application)"}
            }
        }
    },
    {
        "name": "boswell_graph",
        "description": "Get the full memory graph - all nodes (memories) and edges (links). Useful for understanding the topology.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_reflect",
        "description": "Get AI-surfaced insights - highly connected memories and cross-branch patterns.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_commit",
        "description": "Commit a new memory to Boswell. Use this to preserve important decisions, insights, or context worth remembering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to commit to (tint-atlanta, iris, tint-empire, family, command-center, boswell)"},
                "content": {"type": "object", "description": "Memory content as JSON object"},
                "message": {"type": "string", "description": "Commit message describing the memory"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for categorization"}
            },
            "required": ["branch", "content", "message"]
        }
    },
    {
        "name": "boswell_link",
        "description": "Create a resonance link between two memories across branches. Links capture conceptual connections.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_blob": {"type": "string", "description": "Source memory blob hash"},
                "target_blob": {"type": "string", "description": "Target memory blob hash"},
                "source_branch": {"type": "string", "description": "Source branch name"},
                "target_branch": {"type": "string", "description": "Target branch name"},
                "link_type": {"type": "string", "description": "Type: resonance, causal, contradiction, elaboration, application", "default": "resonance"},
                "reasoning": {"type": "string", "description": "Why these memories are connected"}
            },
            "required": ["source_blob", "target_blob", "source_branch", "target_branch", "reasoning"]
        }
    },
    {
        "name": "boswell_checkout",
        "description": "Switch focus to a different cognitive branch.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch to check out"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_startup",
        "description": "Load startup context. Returns commitments + semantically relevant memories. Call FIRST every conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Optional context for semantic retrieval (default: 'important decisions and active commitments')"},
                "k": {"type": "integer", "description": "Number of relevant memories to return (default: 5)", "default": 5}
            }
        }
    },
    {
        "name": "boswell_create_task",
        "description": "Create a new task in the queue. Use to spawn subtasks or add work for yourself or other agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What needs to be done"},
                "branch": {"type": "string", "description": "Which branch this relates to (command-center, tint-atlanta, etc.)"},
                "priority": {"type": "integer", "description": "Priority 1-10 (1=highest, default=5)"},
                "assigned_to": {"type": "string", "description": "Optional: assign to specific instance"},
                "metadata": {"type": "object", "description": "Optional: additional context"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "boswell_claim_task",
        "description": "Claim a task for this agent instance. Prevents other agents from working on it. Use when starting work on a task from the queue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to claim"},
                "instance_id": {"type": "string", "description": "Your unique instance identifier (e.g., 'CC1', 'CW-PM')"}
            },
            "required": ["task_id", "instance_id"]
        }
    },
    {
        "name": "boswell_release_task",
        "description": "Release a claimed task. Use 'completed' when done, 'blocked' if stuck, 'manual' to unclaim without status change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to release"},
                "instance_id": {"type": "string", "description": "Your instance identifier"},
                "reason": {"type": "string", "enum": ["completed", "blocked", "timeout", "manual"], "description": "Why releasing (default: manual)"}
            },
            "required": ["task_id", "instance_id"]
        }
    },
    {
        "name": "boswell_update_task",
        "description": "Update a task's fields (description, status, priority, metadata). Use to report progress or modify task details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to update"},
                "status": {"type": "string", "enum": ["open", "claimed", "blocked", "done"], "description": "New status"},
                "description": {"type": "string", "description": "Updated description"},
                "priority": {"type": "integer", "description": "Priority (1=highest)"},
                "metadata": {"type": "object", "description": "Additional metadata to merge"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_delete_task",
        "description": "Soft delete a task (sets status to 'deleted'). Use to clean up completed or cancelled tasks from the queue.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task ID to delete"}},
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_halt_tasks",
        "description": "EMERGENCY STOP - Halt all task processing. Blocks all claimed tasks, prevents new claims. Use when swarm behavior is problematic.",
        "inputSchema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why halting (default: 'Manual emergency halt')"}}
        }
    },
    {
        "name": "boswell_resume_tasks",
        "description": "Resume task processing after a halt. Clears the halt flag and allows new claims.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_halt_status",
        "description": "Check if the task system is currently halted.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_record_trail",
        "description": "Record a traversal between two memories. Strengthens the path for future recall.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_blob": {"type": "string", "description": "Source memory blob hash"},
                "target_blob": {"type": "string", "description": "Target memory blob hash"}
            },
            "required": ["source_blob", "target_blob"]
        }
    },
    {
        "name": "boswell_hot_trails",
        "description": "Get the strongest memory trails, sorted by strength. These are frequently traversed paths.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max trails to return (default: 20)"}}
        }
    },
    {
        "name": "boswell_trails_from",
        "description": "Get outbound trails from a specific memory. Shows what memories are often accessed after this one.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Source memory blob hash"}},
            "required": ["blob"]
        }
    },
    {
        "name": "boswell_trails_to",
        "description": "Get inbound trails to a specific memory. Shows what memories often lead to this one.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Target memory blob hash"}},
            "required": ["blob"]
        }
    },
]

def mcp_error_response(req_id, code, message):
    """Build JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message}
    }

def mcp_success_response(req_id, result):
    """Build JSON-RPC success response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result
    }


def dispatch_mcp_tool(tool_name, args):
    """
    Dispatch MCP tool call to appropriate Flask view function.
    Returns (result_dict, status_code).
    """
    # ===== READ OPERATIONS =====
    
    if tool_name == "boswell_brief":
        branch = args.get("branch", "command-center")
        return invoke_view(quick_brief, query_string={"branch": branch})
    
    elif tool_name == "boswell_branches":
        return invoke_view(list_branches)
    
    elif tool_name == "boswell_head":
        return invoke_view(get_head, query_string={"branch": args["branch"]})
    
    elif tool_name == "boswell_log":
        qs = {"branch": args["branch"]}
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(get_log, query_string=qs)
    
    elif tool_name == "boswell_search":
        qs = {"q": args["query"]}
        if "branch" in args:
            qs["branch"] = args["branch"]
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(search_memories, query_string=qs)
    
    elif tool_name == "boswell_semantic_search":
        qs = {"q": args["query"]}
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(semantic_search, query_string=qs)
    
    elif tool_name == "boswell_recall":
        qs = {}
        if "hash" in args:
            qs["hash"] = args["hash"]
        if "commit" in args:
            qs["commit"] = args["commit"]
        return invoke_view(recall_memory, query_string=qs)
    
    elif tool_name == "boswell_links":
        qs = {}
        if "branch" in args:
            qs["branch"] = args["branch"]
        if "link_type" in args:
            qs["link_type"] = args["link_type"]
        return invoke_view(list_links, query_string=qs)
    
    elif tool_name == "boswell_graph":
        return invoke_view(get_graph)
    
    elif tool_name == "boswell_reflect":
        return invoke_view(reflect)
    
    elif tool_name == "boswell_startup":
        qs = {}
        if "context" in args:
            qs["context"] = args["context"]
        if "k" in args:
            qs["k"] = args["k"]
        return invoke_view(semantic_startup, query_string=qs)
    
    # ===== WRITE OPERATIONS =====
    
    elif tool_name == "boswell_commit":
        payload = {
            "branch": args["branch"],
            "content": args["content"],
            "message": args["message"],
            "author": "claude-web",
            "type": "memory"
        }
        if "tags" in args:
            payload["tags"] = args["tags"]
        return invoke_view(create_commit, method='POST', json_data=payload)
    
    elif tool_name == "boswell_link":
        payload = {
            "source_blob": args["source_blob"],
            "target_blob": args["target_blob"],
            "source_branch": args["source_branch"],
            "target_branch": args["target_branch"],
            "link_type": args.get("link_type", "resonance"),
            "reasoning": args["reasoning"],
            "created_by": "claude-web"
        }
        return invoke_view(create_link, method='POST', json_data=payload)
    
    elif tool_name == "boswell_checkout":
        return invoke_view(checkout_branch, method='POST', json_data={"branch": args["branch"]})
    
    # ===== TASK QUEUE OPERATIONS =====
    
    elif tool_name == "boswell_create_task":
        payload = {"description": args["description"]}
        for field in ["branch", "priority", "assigned_to", "metadata"]:
            if field in args:
                payload[field] = args[field]
        return invoke_view(create_task, method='POST', json_data=payload)
    
    elif tool_name == "boswell_claim_task":
        task_id = args["task_id"]
        payload = {"instance_id": args["instance_id"]}
        return invoke_view(
            claim_task,
            method='POST',
            path=f'/v2/tasks/{task_id}/claim',
            json_data=payload,
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_release_task":
        task_id = args["task_id"]
        payload = {
            "instance_id": args["instance_id"],
            "reason": args.get("reason", "manual")
        }
        return invoke_view(
            release_task,
            method='POST',
            path=f'/v2/tasks/{task_id}/release',
            json_data=payload,
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_update_task":
        task_id = args["task_id"]
        payload = {}
        for field in ["status", "description", "priority", "metadata"]:
            if field in args:
                payload[field] = args[field]
        return invoke_view(
            update_task,
            method='PATCH',
            path=f'/v2/tasks/{task_id}',
            json_data=payload,
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_delete_task":
        task_id = args["task_id"]
        return invoke_view(
            delete_task,
            method='DELETE',
            path=f'/v2/tasks/{task_id}',
            view_args={"task_id": task_id}
        )
    
    elif tool_name == "boswell_halt_tasks":
        payload = {}
        if "reason" in args:
            payload["reason"] = args["reason"]
        return invoke_view(halt_tasks, method='POST', json_data=payload)
    
    elif tool_name == "boswell_resume_tasks":
        return invoke_view(resume_tasks, method='POST', json_data={})
    
    elif tool_name == "boswell_halt_status":
        return invoke_view(halt_status)
    
    # ===== TRAIL OPERATIONS =====
    
    elif tool_name == "boswell_record_trail":
        payload = {
            "source_blob": args["source_blob"],
            "target_blob": args["target_blob"]
        }
        return invoke_view(record_trail, method='POST', json_data=payload)
    
    elif tool_name == "boswell_hot_trails":
        qs = {}
        if "limit" in args:
            qs["limit"] = args["limit"]
        return invoke_view(get_hot_trails, query_string=qs if qs else None)
    
    elif tool_name == "boswell_trails_from":
        blob = args["blob"]
        return invoke_view(
            get_trails_from,
            path=f'/v2/trails/from/{blob}',
            view_args={"source_blob": blob}
        )
    
    elif tool_name == "boswell_trails_to":
        blob = args["blob"]
        return invoke_view(
            get_trails_to,
            path=f'/v2/trails/to/{blob}',
            view_args={"target_blob": blob}
        )
    
    else:
        return {"error": f"Unknown tool: {tool_name}"}, 400


@app.route('/v2/mcp', methods=['POST'])
def mcp_handler():
    """
    MCP Streamable HTTP endpoint.
    Handles JSON-RPC 2.0 requests: initialize, tools/list, tools/call
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(mcp_error_response(None, -32700, "Parse error: empty body")), 400
    except Exception as e:
        return jsonify(mcp_error_response(None, -32700, f"Parse error: {str(e)}")), 400
    
    req_id = data.get("id")
    method = data.get("method")
    params = data.get("params", {})
    
    # Log for audit
    print(f"[MCP] method={method} id={req_id}", file=sys.stderr)
    
    # ===== INITIALIZE =====
    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": MCP_SERVER_NAME,
                "version": MCP_SERVER_VERSION
            },
            "capabilities": {
                "tools": {"listChanged": False}
            }
        }
        return jsonify(mcp_success_response(req_id, result))
    
    # ===== TOOLS/LIST =====
    elif method == "tools/list":
        result = {"tools": MCP_TOOLS}
        return jsonify(mcp_success_response(req_id, result))
    
    # ===== TOOLS/CALL =====
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        
        if not tool_name:
            return jsonify(mcp_error_response(req_id, -32602, "Missing tool name")), 400
        
        # Dispatch to view function
        start_time = time.time()
        result_data, status_code = dispatch_mcp_tool(tool_name, tool_args)
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log tool call for audit
        print(f"[MCP] tool={tool_name} status={status_code} duration={duration_ms}ms", file=sys.stderr)
        
        # Build MCP response
        if status_code >= 400:
            # Return error in MCP format (but with 200 HTTP - MCP convention)
            error_text = result_data.get('error', 'Unknown error') if isinstance(result_data, dict) else str(result_data)
            result = {
                "content": [{"type": "text", "text": f"Error: {error_text}"}],
                "isError": True
            }
        else:
            # Success - serialize result as text content
            result = {
                "content": [{"type": "text", "text": json.dumps(result_data, indent=2, default=str)}]
            }
        
        return jsonify(mcp_success_response(req_id, result))
    
    # ===== UNKNOWN METHOD =====
    else:
        return jsonify(mcp_error_response(req_id, -32601, f"Method not found: {method}")), 400


# Convenience endpoint for MCP health check
@app.route('/v2/mcp/health', methods=['GET'])
def mcp_health():
    """Health check for MCP endpoint."""
    return jsonify({
        "status": "ok",
        "server": MCP_SERVER_NAME,
        "version": MCP_SERVER_VERSION,
        "protocol": MCP_PROTOCOL_VERSION,
        "tools_count": len(MCP_TOOLS)
    })


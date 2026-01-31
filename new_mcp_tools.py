# Whisper-enabled MCP_TOOLS - behavioral hints embedded in descriptions
MCP_TOOLS = [
    {
        "name": "boswell_startup",
        "description": "Load startup context. Returns sacred commitments, open tasks, and relevant memories. CALL THIS FIRST at conversation start, before responding to anything—even 'hi'. Sets the stage for continuity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Optional context for semantic retrieval (default: 'important decisions and active commitments')"},
                "k": {"type": "integer", "description": "Number of relevant memories to return (default: 5)", "default": 5}
            }
        }
    },
    {
        "name": "boswell_brief",
        "description": "Quick context snapshot—recent commits, open tasks, branch activity. Call when resuming work or when asked 'what's been happening?' Lighter than boswell_startup.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to focus on (default: command-center)", "default": "command-center"}
            }
        }
    },
    {
        "name": "boswell_branches",
        "description": "List all cognitive branches: command-center (infrastructure), tint-atlanta (CRM), iris (research), tint-empire (franchise), family (personal), boswell (memory system). Use to understand the topology.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_head",
        "description": "Get the current HEAD commit for a branch. Use to check what was last committed.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch name (e.g., tint-atlanta, command-center, boswell)"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_log",
        "description": "View commit history for a branch. Use to trace what happened, find specific decisions, or understand work progression.",
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
        "description": "Keyword search across all memories. Call BEFORE answering questions about past work when immediate context is missing. If asked 'what were we doing?' and you don't know, search first.",
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
        "description": "Find conceptually related memories using AI embeddings. Use for fuzzy queries like 'decisions about architecture' or when keyword search misses context. Complements boswell_search.",
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
        "description": "Retrieve a specific memory by its blob hash or commit hash. Use when you have a hash reference and need full content.",
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
        "description": "List resonance links between memories. Use to see cross-branch connections and conceptual relationships.",
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
        "description": "Get full memory graph—nodes and edges. Use for topology analysis or visualization.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_reflect",
        "description": "Get AI-surfaced insights—highly connected memories and cross-branch patterns. Use for strategic review.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_commit",
        "description": "Preserve a decision, insight, or context to memory. ALWAYS capture WHY, not just WHAT—future instances need reasoning. Call after completing steps, solving problems, making decisions, or learning something new.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch to commit to (tint-atlanta, iris, tint-empire, family, command-center, boswell)"},
                "content": {"type": "object", "description": "Memory content as JSON object"},
                "message": {"type": "string", "description": "Commit message describing the memory"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for categorization"},
                "force_branch": {"type": "boolean", "description": "Suppress routing warnings - use when intentionally committing to a branch despite mismatch"}
            },
            "required": ["branch", "content", "message"]
        }
    },
    {
        "name": "boswell_link",
        "description": "Create a resonance link between two memories. Captures conceptual connections across branches. Explain the reasoning—links are for pattern discovery.",
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
        "description": "Switch focus to a different branch. Use when changing work contexts.",
        "inputSchema": {
            "type": "object",
            "properties": {"branch": {"type": "string", "description": "Branch to check out"}},
            "required": ["branch"]
        }
    },
    {
        "name": "boswell_create_task",
        "description": "Add a task to the queue for yourself or other agents. Use to spawn subtasks, track work, or hand off to other instances.",
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
        "description": "Claim a task to prevent other agents from working on it. Call when starting work from the queue. Always provide your instance_id.",
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
        "description": "Release a claimed task. Use 'completed' when done, 'blocked' if stuck, 'manual' to just unclaim. Always release what you claim.",
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
        "description": "Update task status, description, or priority. Use to report progress or modify details. Good practice: update status as you work.",
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
        "description": "Soft-delete a task. Use for cleanup after completion or cancellation.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task ID to delete"}},
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_halt_tasks",
        "description": "EMERGENCY STOP. Halts all task processing, blocks claims. Use when swarm behavior is problematic or coordination breaks down.",
        "inputSchema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why halting (default: 'Manual emergency halt')"}}
        }
    },
    {
        "name": "boswell_resume_tasks",
        "description": "Resume task processing after a halt. Clears the halt flag.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_halt_status",
        "description": "Check if task system is halted. Call before claiming tasks if unsure.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "boswell_record_trail",
        "description": "Record a traversal between memories. Strengthens the path for future recall. Trails that aren't traversed decay over time.",
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
        "description": "Get strongest memory trails—frequently traversed paths. Shows what's top of mind.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max trails to return (default: 20)"}}
        }
    },
    {
        "name": "boswell_trails_from",
        "description": "Get outbound trails from a memory. Shows what's typically accessed next.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Source memory blob hash"}},
            "required": ["blob"]
        }
    },
    {
        "name": "boswell_trails_to",
        "description": "Get inbound trails to a memory. Shows what typically leads here.",
        "inputSchema": {
            "type": "object",
            "properties": {"blob": {"type": "string", "description": "Target memory blob hash"}},
            "required": ["blob"]
        }
    },
    {
        "name": "boswell_trail_health",
        "description": "Trail system health—state distribution (ACTIVE/FADING/DORMANT/ARCHIVED), activity metrics. Use to monitor memory decay.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "boswell_buried_memories",
        "description": "Find dormant and archived trails—memory paths fading from recall. These can be resurrected by traversing them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max trails to return (default: 20)"},
                "include_archived": {"type": "boolean", "description": "Include archived trails (default: true)"}
            }
        }
    },
    {
        "name": "boswell_decay_forecast",
        "description": "Predict when trails will decay. Use to identify memories at risk of fading.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "boswell_resurrect",
        "description": "Resurrect a dormant trail by traversing it. Doubles strength, resets to ACTIVE. Use to save important paths from decay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trail_id": {"type": "string", "description": "Trail ID to resurrect"},
                "source_blob": {"type": "string", "description": "Or: source blob hash"},
                "target_blob": {"type": "string", "description": "Or: target blob hash"}
            }
        }
    },
    {
        "name": "boswell_checkpoint",
        "description": "Save session checkpoint for crash recovery. Captures WHERE you are—progress, next step, context. Use before risky operations or long tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to checkpoint"},
                "instance_id": {"type": "string", "description": "Your instance identifier (e.g., 'CC1', 'CW-Opus')"},
                "progress": {"type": "string", "description": "Human-readable progress description"},
                "next_step": {"type": "string", "description": "What to do next on resume"},
                "context_snapshot": {"type": "object", "description": "Arbitrary context data to preserve"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_resume",
        "description": "Get checkpoint for a task. Use to resume after crash or context loss.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to resume"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "boswell_validate_routing",
        "description": "Check which branch best matches content before committing. Returns confidence scores. Use when unsure about branch selection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "object", "description": "Content to analyze"},
                "branch": {"type": "string", "description": "Requested branch"}
            },
            "required": ["content"]
        }
    },
    # ==================== IMMUNE SYSTEM TOOLS ====================
    {
        "name": "boswell_quarantine_list",
        "description": "List all quarantined memories awaiting human review. Quarantined memories are anomalies detected by the immune system patrol. Review and resolve them with boswell_quarantine_resolve.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max entries to return (default: 50)", "default": 50}
            }
        }
    },
    {
        "name": "boswell_quarantine_resolve",
        "description": "Resolve a quarantined memory: reinstate it to active status or permanently delete it. Always provide a reason explaining your decision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blob_hash": {"type": "string", "description": "Hash of the quarantined blob"},
                "action": {"type": "string", "enum": ["reinstate", "delete"], "description": "Whether to reinstate or delete"},
                "reason": {"type": "string", "description": "Why you're reinstating or deleting this memory"}
            },
            "required": ["blob_hash", "action"]
        }
    },
    {
        "name": "boswell_immune_status",
        "description": "Get immune system health: quarantine counts, last patrol time, branch health scores. Use to monitor memory graph health.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
]

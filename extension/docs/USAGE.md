# Boswell Usage Guide

Boswell is your AI's persistent memory system. Think of it as "git for your conversations" - you can commit important context, search past interactions, and build a knowledge graph that grows with you.

## Getting Started

Every conversation should start with:

```
Use boswell_startup
```

This loads your sacred manifest (active commitments) and tool registry, giving Claude context about what matters to you.

---

## The 13 Boswell Tools

### 1. boswell_startup
**Load startup context - call this FIRST in every conversation**

```
Use boswell_startup
```

Returns:
- Sacred manifest (your active commitments and priorities)
- Tool registry (available tools and their purposes)

**Best Practice**: Add "Call boswell_startup" to Claude's custom instructions so it runs automatically.

---

### 2. boswell_brief
**Get a quick summary of recent activity**

```
Use boswell_brief
```

Parameters:
- `branch` (optional): Focus on a specific branch (default: command-center)

Returns recent commits, pending sessions, and branch status. Great for catching up at the start of a session.

---

### 3. boswell_commit
**Save a memory - preserves important decisions and context**

```
Use boswell_commit with:
- branch: "command-center"
- message: "Decided to use PostgreSQL for the project"
- content: { "type": "decision", "details": "..." }
- tags: ["database", "architecture"]
```

Parameters:
- `branch` (required): Which branch to commit to
- `message` (required): Short description of what you're saving
- `content` (required): JSON object with the memory details
- `tags` (optional): Array of tags for easier searching

**When to commit:**
- Important decisions
- Project milestones
- Learned preferences
- Configuration choices
- Meeting summaries

---

### 4. boswell_search
**Search your memories by keyword**

```
Use boswell_search with query: "database"
```

Parameters:
- `query` (required): Search term
- `branch` (optional): Limit to specific branch
- `limit` (optional): Max results (default: 10)

Returns matching memories with commit info and relevance scores.

---

### 5. boswell_recall
**Retrieve a specific memory by its hash**

```
Use boswell_recall with hash: "abc123..."
```

Parameters:
- `hash`: Blob hash from search results
- `commit`: Or use commit hash instead

Returns the full content of a specific memory.

---

### 6. boswell_log
**View commit history for a branch**

```
Use boswell_log with branch: "command-center"
```

Parameters:
- `branch` (required): Branch name
- `limit` (optional): Max commits (default: 10)

Shows recent commits like `git log` - useful for reviewing what's been saved.

---

### 7. boswell_branches
**List all cognitive branches**

```
Use boswell_branches
```

Returns all your branches. Default branches:
- `command-center` - Infrastructure, deployments, tooling
- `tint-atlanta` - CRM/business work
- `iris` - Research/BCI projects
- `tint-empire` - Franchise work
- `family` - Personal projects
- `boswell` - Memory system meta

---

### 8. boswell_head
**Get the latest commit on a branch**

```
Use boswell_head with branch: "command-center"
```

Returns the most recent commit hash and message for a branch.

---

### 9. boswell_checkout
**Switch focus to a different branch**

```
Use boswell_checkout with branch: "iris"
```

Changes the active branch context. Use this when switching between projects.

---

### 10. boswell_graph
**Visualize your memory graph**

```
Use boswell_graph
```

Returns all nodes (memories) and edges (links) in your knowledge graph. Useful for understanding connections.

---

### 11. boswell_links
**See connections between memories**

```
Use boswell_links
```

Parameters:
- `branch` (optional): Filter by branch
- `link_type` (optional): Filter by type (resonance, causal, etc.)

Shows cross-branch connections and relationships.

---

### 12. boswell_link
**Create a connection between two memories**

```
Use boswell_link with:
- source_blob: "abc123"
- target_blob: "def456"
- source_branch: "command-center"
- target_branch: "iris"
- reasoning: "This decision affects the research project"
```

Creates a resonance link between memories, building your knowledge graph.

---

### 13. boswell_reflect
**Get AI-generated insights from your memories**

```
Use boswell_reflect
```

Analyzes your memory graph and surfaces:
- Highly connected memories (important nodes)
- Patterns across branches
- Suggested connections

---

## Workflows

### Daily Standup
```
1. boswell_startup
2. boswell_brief
3. Review what needs attention
4. Commit any new decisions
```

### Starting a New Project
```
1. boswell_checkout to project branch
2. boswell_commit initial context
3. boswell_link to related memories
```

### Research Session
```
1. boswell_search for related prior work
2. Work on research
3. boswell_commit findings
4. boswell_reflect to find patterns
```

### End of Day
```
1. Review what was accomplished
2. boswell_commit important outcomes
3. boswell_link any cross-project insights
```

---

## Tips

1. **Commit often** - Small, frequent commits are better than rare large ones
2. **Use meaningful messages** - Future you will thank present you
3. **Tag consistently** - Makes searching much easier
4. **Link across branches** - The magic is in the connections
5. **Start with startup** - Always begin with `boswell_startup`

---

## Need Help?

- **Docs**: https://askboswell.com/docs
- **Support**: support@askboswell.com

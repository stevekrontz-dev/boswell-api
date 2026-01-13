# Boswell Quick Reference Card

## Essential Commands

| Command | What it does |
|---------|-------------|
| `boswell_startup` | **Start here!** Loads your context |
| `boswell_brief` | Quick status summary |
| `boswell_commit` | Save a memory |
| `boswell_search` | Find memories |

## All 13 Tools

### Memory Operations
```
boswell_commit    - Save new memory
boswell_recall    - Get specific memory by hash
boswell_search    - Search memories by keyword
```

### Branch Operations
```
boswell_branches  - List all branches
boswell_checkout  - Switch to branch
boswell_head      - Latest commit on branch
boswell_log       - Commit history
```

### Graph Operations
```
boswell_graph     - Full memory graph
boswell_links     - List connections
boswell_link      - Create connection
boswell_reflect   - AI insights
```

### Session
```
boswell_startup   - Load context (FIRST!)
boswell_brief     - Quick summary
```

## Common Patterns

**Start every conversation:**
```
Use boswell_startup
```

**Save a decision:**
```
Use boswell_commit with:
- branch: "command-center"
- message: "Chose React for frontend"
- content: {"type": "decision", "choice": "React"}
```

**Find something:**
```
Use boswell_search with query: "database"
```

**Switch projects:**
```
Use boswell_checkout with branch: "project-name"
```

## Default Branches

| Branch | Purpose |
|--------|---------|
| `command-center` | Infrastructure & tools |
| `tint-atlanta` | CRM/business |
| `iris` | Research/BCI |
| `tint-empire` | Franchise |
| `family` | Personal |
| `boswell` | Memory system |

## Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| "Tool not found" | Restart Claude Desktop |
| "Auth error" | Check API key in dashboard |
| "No results" | Try broader search terms |
| "Can't commit" | Check branch name exists |

## Support

- Docs: askboswell.com/docs
- Email: support@askboswell.com

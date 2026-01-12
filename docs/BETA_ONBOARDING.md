# Boswell Beta Onboarding Guide

Welcome to Boswell - your AI's persistent memory system.

## What is Boswell?

Boswell is a **memory layer for Claude** that persists across conversations. Instead of starting fresh every time, Claude can:

- **Remember** decisions, context, and progress from previous sessions
- **Organize** memories into cognitive branches (projects, domains, life areas)
- **Search** across all stored knowledge
- **Connect** related memories through resonance links
- **Reflect** on patterns and surface insights

Think of it as giving Claude a second brain that survives beyond the chat window.

## Why Boswell?

Without Boswell:
- Every conversation starts from zero
- You repeat context constantly
- Complex projects lose continuity
- Claude forgets what worked before

With Boswell:
- Claude picks up where you left off
- Project history is instantly available
- Decisions and rationale are preserved
- Cross-project insights emerge automatically

---

## Quick Start: Connect Boswell to Claude

### Step 1: Get Your Credentials

Your beta credentials:
- **API Endpoint**: `https://delightful-imagination-production-f6a1.up.railway.app`
- **Tenant ID**: (provided in your welcome email)
- **API Key**: (provided in your welcome email)

### Step 2: Add the MCP Connector

Add this to your Claude Desktop configuration file:

**Location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Configuration:**

```json
{
  "mcpServers": {
    "boswell": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic/boswell-mcp"
      ],
      "env": {
        "BOSWELL_API_URL": "https://delightful-imagination-production-f6a1.up.railway.app",
        "BOSWELL_TENANT_ID": "your-tenant-id-here",
        "BOSWELL_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Step 3: Restart Claude Desktop

Close and reopen Claude Desktop. You should see the Boswell tools available in the tools menu.

### Step 4: Verify Connection

Ask Claude:
```
Call boswell_brief to check the memory system status.
```

If connected, you'll see a summary of recent activity and available branches.

---

## Your First Commands

### Start Every Session Right

```
Call boswell_startup to load context.
```

This loads your active commitments and available tools in one call. Make this your first action in important conversations.

### Check What's Happening

```
Call boswell_brief to see recent activity.
```

Shows recent commits across all branches, pending items, and system status.

### Store a Memory

```
Commit this to Boswell on the [branch-name] branch: [your memory content]
```

Example:
```
Commit to Boswell on command-center: Deployed new API endpoint for user authentication. Used JWT with 24-hour expiry. Password hashing with bcrypt.
```

### Search Your Memories

```
Search Boswell for "authentication"
```

Finds all memories mentioning that term across all branches.

### Check a Specific Branch

```
Show me the last 10 commits on the command-center branch.
```

---

## Understanding Branches

Boswell organizes memories into **cognitive branches** - think of them as mental folders for different life domains:

| Branch | Purpose |
|--------|---------|
| `command-center` | Infrastructure, deployments, tooling |
| `work` | Professional projects (customize as needed) |
| `personal` | Personal projects and notes |
| `research` | Learning, exploration, experiments |

You can create custom branches for specific projects. Ask Claude to commit to any branch name and it will be created automatically.

---

## Example Workflows

### Project Continuity

**Session 1:**
```
I just finished implementing the login flow. Commit to Boswell:
- Used OAuth 2.0 with Google provider
- Tokens stored in httpOnly cookies
- Session expires after 7 days
- Still need to add refresh token rotation
```

**Session 2 (days later):**
```
Search Boswell for "login" and remind me where we left off.
```

Claude retrieves your exact context and continues seamlessly.

### Decision Documentation

```
Commit to Boswell: DECISION - chose PostgreSQL over MongoDB for user data.
Reasons: ACID compliance needed for financial transactions,
team has more SQL experience, better tooling ecosystem.
```

Later, when someone asks "why Postgres?", Claude can find and explain the rationale.

### Cross-Project Insights

```
Call boswell_reflect to see patterns across my memories.
```

Surfaces connections you might have missed - similar problems solved in different projects, recurring themes, etc.

---

## All Boswell Commands

| Command | What it does |
|---------|-------------|
| `boswell_startup` | Load full context (sacred manifest + tools) |
| `boswell_brief` | Quick status of recent activity |
| `boswell_commit` | Store a new memory |
| `boswell_search` | Find memories by keyword |
| `boswell_log` | View commit history for a branch |
| `boswell_recall` | Retrieve a specific memory by hash |
| `boswell_branches` | List all your branches |
| `boswell_head` | Get current HEAD of a branch |
| `boswell_reflect` | AI-surfaced insights and patterns |
| `boswell_links` | View connections between memories |
| `boswell_link` | Create a resonance link between memories |
| `boswell_graph` | Get the full memory graph |
| `boswell_checkout` | Switch focus to a different branch |

---

## FAQ

### How much can I store?

Beta accounts include generous storage. Commit freely - that's what it's for.

### Are my memories private?

Yes. Each tenant is completely isolated. Your memories are encrypted at rest and only accessible with your API key.

### Can I delete memories?

Currently, Boswell is append-only (like git). We're considering selective deletion for a future release.

### What if Claude doesn't use Boswell?

Gently remind it: "Remember to commit important decisions to Boswell" or start sessions with "Call boswell_startup first."

### Can multiple Claude instances share memory?

Yes! That's a key feature. Different Claude sessions (Desktop, API, multiple terminals) all read/write to the same memory store. This enables:
- Continuity across devices
- Team collaboration (coming soon)
- Multi-agent coordination

### What's a "resonance link"?

A connection between two memories across different branches. Example: a technical decision in `work` that relates to a research finding in `research`. Use `boswell_link` to create these explicitly, or let `boswell_reflect` surface them automatically.

---

## Troubleshooting

### "Boswell tools not appearing"

1. Check your config file syntax (valid JSON?)
2. Ensure environment variables are set correctly
3. Restart Claude Desktop completely
4. Check Claude's MCP logs for errors

### "Authentication failed"

- Verify your API key is correct (no extra spaces)
- Confirm your tenant ID matches what was provided
- Check if your beta access has been activated

### "Connection timeout"

- Check your internet connection
- The API might be briefly unavailable - retry in a few minutes
- Ensure the API URL is exactly as shown (no trailing slash)

### "Empty results from search"

- You might not have committed anything yet!
- Try broader search terms
- Check you're searching the right branch (or omit branch to search all)

---

## Getting Help

- **Issues**: Report bugs or feature requests to your beta coordinator
- **Questions**: Ask in the beta Slack channel (invite in welcome email)
- **Feedback**: We want to hear everything - what works, what doesn't, what's confusing

---

## What's Next?

During beta, we're actively building:
- **Web dashboard** for browsing memories visually
- **Team sharing** for collaborative memory
- **Smarter reflection** with deeper pattern analysis
- **Integrations** with other tools and workflows

Your feedback shapes what we build. Use Boswell, break Boswell, tell us about it.

---

*Welcome to the beta. Let's give AI a memory worth having.*

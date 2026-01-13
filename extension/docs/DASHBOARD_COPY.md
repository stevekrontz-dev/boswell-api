# Dashboard Copy for CC3

Copy for the Boswell dashboard UI. Use these exact strings for consistency.

---

## Connect Page (Extension Download)

### Hero Section
**Headline:** Connect Boswell to Claude Desktop
**Subhead:** Give your AI persistent memory in under 60 seconds.

### Download Button
**Button Text:** Download Extension
**Button Subtext:** boswell.mcpb (~4 MB)

### Steps Section
**Section Title:** How it works

**Step 1:**
- Icon: Download
- Title: Download
- Text: Click the button above to get your personalized extension bundle.

**Step 2:**
- Icon: Click/Tap
- Title: Install
- Text: Double-click the downloaded file. Claude Desktop handles the rest.

**Step 3:**
- Icon: Chat bubble
- Title: Start remembering
- Text: Say "boswell_startup" in any conversation. You're connected!

### Features List
**Section Title:** What you get

- **13 memory tools** - Commit, search, recall, link, and more
- **Cross-conversation context** - Pick up where you left off
- **Knowledge graph** - Build connections across projects
- **Sacred manifest** - Never forget your commitments
- **Instant sync** - Your memories live in the cloud

### Requirements
**Section Title:** Requirements

- Claude Desktop 1.0.0+
- macOS, Windows, or Linux
- Active Boswell subscription

---

## Dashboard Home

### Welcome Card (New Users)
**Title:** Welcome to Boswell
**Text:** Your AI's memory system is ready. Download the extension to connect Claude Desktop.
**CTA:** Get Started →

### Welcome Card (Connected Users)
**Title:** You're connected
**Text:** Boswell is active in Claude Desktop. Start any conversation with `boswell_startup`.
**CTA:** View Usage Guide →

### Stats Card
**Title:** Your Memory Stats
- **Commits this week:** {count}
- **Total memories:** {count}
- **Active branches:** {count}
- **Connections:** {count}

---

## Settings Page

### API Keys Section
**Title:** API Keys
**Description:** Manage your API keys for Boswell access. Keep these secret!

**Create Key Button:** + New API Key
**Key Created Modal:**
- Title: API Key Created
- Text: Copy this key now. You won't see it again.
- Warning: Store this securely. If lost, create a new key.

### Subscription Section
**Title:** Your Plan
**Current Plan Label:** Current plan
**Upgrade CTA:** Upgrade Plan

---

## Error Messages

### Connection Errors
- **No API Key:** "Create an API key to connect Boswell."
- **Invalid Key:** "This API key is invalid or expired. Create a new one."
- **Network Error:** "Can't reach Boswell. Check your connection."

### Download Errors
- **Not Logged In:** "Log in to download your extension."
- **No Subscription:** "Subscribe to download the extension."
- **Generation Failed:** "Couldn't create your bundle. Try again."

---

## Success Messages

- **Key Created:** "API key created. Copy it now!"
- **Key Revoked:** "API key revoked successfully."
- **Extension Downloaded:** "Extension ready! Double-click to install."
- **Settings Saved:** "Settings saved."

---

## Empty States

### No Memories Yet
**Title:** No memories yet
**Text:** Start using Boswell in Claude Desktop. Say "boswell_commit" to save your first memory.
**CTA:** Learn How →

### No API Keys
**Title:** No API keys
**Text:** Create an API key to authenticate with Boswell.
**CTA:** + Create Key

---

## Footer Links
- Documentation
- Support
- Status
- Privacy Policy
- Terms of Service

---

## Tooltips

- **API Key:** "Used to authenticate your Claude Desktop with Boswell"
- **Tenant ID:** "Your unique Boswell account identifier"
- **Branch:** "A category for organizing memories (like a folder)"
- **Commit:** "A saved memory with a message and content"

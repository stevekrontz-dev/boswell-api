# Boswell Extension Installation Guide

## Prerequisites

- **Claude Desktop** version 1.0.0 or later
- **Node.js** 18.0.0 or later (included with Claude Desktop)

## Quick Install

1. Log in to your [Boswell Dashboard](https://askboswell.com/dashboard)
2. Click **"Download Extension"**
3. Double-click the downloaded `boswell.mcpb` file
4. Claude Desktop will automatically install and configure Boswell

That's it! Your credentials are pre-configured in the bundle.

---

## Platform-Specific Instructions

### macOS

1. Download `boswell.mcpb` from your dashboard
2. Locate the file in Finder (usually in Downloads)
3. Double-click `boswell.mcpb`
4. Claude Desktop opens and prompts: "Install Boswell Memory?"
5. Click **Install**
6. Restart Claude Desktop when prompted

**Verification:**
- Open Claude Desktop
- Type: "Use boswell_startup"
- You should see your sacred manifest and tool registry

### Windows

1. Download `boswell.mcpb` from your dashboard
2. Locate the file in File Explorer (usually in Downloads)
3. Double-click `boswell.mcpb`
4. If Windows asks "How do you want to open this file?", select Claude Desktop
5. Click **Install** when prompted
6. Restart Claude Desktop

**Troubleshooting Windows:**
- If the file doesn't open, right-click → "Open with" → Claude Desktop
- Ensure Windows Defender isn't blocking the file
- Run Claude Desktop as Administrator if needed

### Linux

1. Download `boswell.mcpb` from your dashboard
2. Open terminal in the download directory
3. Run: `claude-desktop install boswell.mcpb`
4. Or double-click if your desktop environment supports it
5. Restart Claude Desktop

**For Snap/Flatpak installations:**
```bash
# Snap
snap run claude-desktop --install ~/Downloads/boswell.mcpb

# Flatpak
flatpak run com.anthropic.claude-desktop --install ~/Downloads/boswell.mcpb
```

---

## Manual Installation (Advanced)

If automatic installation fails, you can manually configure Boswell:

1. Extract `boswell.mcpb` (it's a ZIP file):
   ```bash
   unzip boswell.mcpb -d boswell-extension
   ```

2. Copy `server/` to Claude Desktop's extensions directory:
   - **macOS**: `~/Library/Application Support/Claude/extensions/boswell/`
   - **Windows**: `%APPDATA%\Claude\extensions\boswell\`
   - **Linux**: `~/.config/claude/extensions/boswell/`

3. Add to Claude Desktop's config (`claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "boswell": {
         "command": "node",
         "args": ["<path-to>/server/index.js"],
         "env": {
           "BOSWELL_API_KEY": "your_api_key",
           "BOSWELL_TENANT_ID": "your_tenant_id",
           "BOSWELL_API_ENDPOINT": "https://boswell-api-production.up.railway.app"
         }
       }
     }
   }
   ```

4. Restart Claude Desktop

---

## Verify Installation

After installation, verify Boswell is working:

1. Open Claude Desktop
2. Start a new conversation
3. Say: "Call boswell_startup"

You should see output like:
```
Sacred Manifest loaded: [your commitments]
Tool Registry loaded: [available tools]
```

If you see an error, check:
- Your API key is valid (dashboard → API Keys)
- You have an active subscription
- Claude Desktop has been restarted

---

## Updating Boswell

When a new version is available:

1. Go to your [Boswell Dashboard](https://askboswell.com/dashboard)
2. Click **"Download Extension"** (always downloads latest)
3. Install over existing version
4. Restart Claude Desktop

Your memories and settings are stored in the cloud - updating won't lose any data.

---

## Uninstalling

### From Claude Desktop
1. Open Claude Desktop Settings
2. Go to Extensions
3. Find "Boswell Memory"
4. Click **Uninstall**

### Manual Removal
Delete the extension directory:
- **macOS**: `rm -rf ~/Library/Application Support/Claude/extensions/boswell`
- **Windows**: Delete `%APPDATA%\Claude\extensions\boswell`
- **Linux**: `rm -rf ~/.config/claude/extensions/boswell`

---

## Getting Help

- **Documentation**: https://askboswell.com/docs
- **Support**: support@askboswell.com
- **Status**: https://status.askboswell.com

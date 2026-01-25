import { useState } from 'react';

export default function QuickConnect() {
  const [copied, setCopied] = useState(false);
  const MCP_URL = 'https://delightful-imagination-production-f6a1.up.railway.app/v2/mcp';

  const copyUrl = () => {
    navigator.clipboard.writeText(MCP_URL);
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-ink-950 via-ink-900 to-ink-950 flex flex-col items-center justify-center p-6">
      {/* Logo */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-bold text-parchment-50 mb-2">Boswell</h1>
        <p className="text-parchment-200/60">Memory for Claude</p>
      </div>

      {/* Main card */}
      <div className="w-full max-w-lg bg-ink-900/80 border border-parchment-50/10 rounded-2xl p-8 shadow-2xl">
        <h2 className="text-2xl font-semibold text-parchment-50 mb-6 text-center">
          Connect in 30 seconds
        </h2>

        {/* Steps */}
        <div className="space-y-6">
          {/* Step 1 */}
          <div className="flex gap-4">
            <div className="flex-shrink-0 w-8 h-8 bg-orange-500 rounded-full flex items-center justify-center text-white font-bold">
              1
            </div>
            <div className="flex-1">
              <p className="text-parchment-100 font-medium mb-2">Copy this URL</p>
              <div className="flex items-center gap-2 bg-ink-800 rounded-lg p-3">
                <code className="flex-1 text-sm text-parchment-200 break-all font-mono">
                  {MCP_URL}
                </code>
                <button
                  onClick={copyUrl}
                  className="px-4 py-2 bg-orange-500 hover:bg-orange-400 text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
                >
                  {copied ? '✓ Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          </div>

          {/* Step 2 */}
          <div className="flex gap-4">
            <div className="flex-shrink-0 w-8 h-8 bg-orange-500 rounded-full flex items-center justify-center text-white font-bold">
              2
            </div>
            <div className="flex-1">
              <p className="text-parchment-100 font-medium mb-2">Open Claude Settings</p>
              <a
                href="https://claude.ai/settings/integrations"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-5 py-3 bg-ink-800 hover:bg-ink-700 border border-parchment-50/20 text-parchment-100 font-medium rounded-lg transition-colors"
              >
                Open Settings →
              </a>
              <p className="text-parchment-200/50 text-sm mt-2">
                (Requires Pro, Max, Team, or Enterprise plan)
              </p>
            </div>
          </div>

          {/* Step 3 */}
          <div className="flex gap-4">
            <div className="flex-shrink-0 w-8 h-8 bg-orange-500 rounded-full flex items-center justify-center text-white font-bold">
              3
            </div>
            <div className="flex-1">
              <p className="text-parchment-100 font-medium mb-2">Add Custom Connector</p>
              <ol className="text-parchment-200/70 text-sm space-y-1 list-decimal list-inside">
                <li>Scroll to "Custom Connectors"</li>
                <li>Click "Add custom connector"</li>
                <li>Paste the URL you copied</li>
                <li>Click "Add"</li>
              </ol>
            </div>
          </div>
        </div>

        {/* Done state */}
        <div className="mt-8 p-4 bg-green-900/20 border border-green-500/30 rounded-lg text-center">
          <p className="text-green-400 font-medium">That's it!</p>
          <p className="text-parchment-200/60 text-sm mt-1">
            Claude will now remember things across conversations.
          </p>
        </div>
      </div>

      {/* Footer links */}
      <div className="mt-8 flex gap-6 text-sm text-parchment-200/40">
        <a href="/login" className="hover:text-parchment-200 transition-colors">
          Sign in to dashboard
        </a>
        <a href="/signup" className="hover:text-parchment-200 transition-colors">
          Create account
        </a>
      </div>
    </div>
  );
}

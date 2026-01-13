import { useState } from 'react';

export default function Connect() {
  const [activeTab, setActiveTab] = useState<'desktop' | 'code' | 'web'>('code');
  const [copied, setCopied] = useState(false);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const mcpCommand = 'claude mcp add boswell --url https://delightful-imagination-production-f6a1.up.railway.app/mcp';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Connect Boswell</h1>
        <p className="text-slate-400 mt-1">Choose how you want to connect Boswell to Claude.</p>
      </div>

      <div className="flex gap-2 border-b border-slate-800">
        {(['desktop', 'code', 'web'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={'px-4 py-2 text-sm font-medium border-b-2 transition-colors ' +
              (activeTab === tab
                ? 'border-orange-500 text-orange-400'
                : 'border-transparent text-slate-400 hover:text-slate-200')
            }
          >
            {tab === 'desktop' && 'Desktop Extension'}
            {tab === 'code' && 'Claude Code'}
            {tab === 'web' && 'Claude.ai (Web)'}
          </button>
        ))}
      </div>

      <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
        {activeTab === 'desktop' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-100">Desktop Extension</h3>
            <p className="text-slate-400">Download the Boswell extension for your desktop Claude app.</p>
            <button className="px-4 py-2 bg-slate-800 text-slate-400 rounded-lg cursor-not-allowed">
              Coming Soon
            </button>
          </div>
        )}

        {activeTab === 'code' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-100">Claude Code</h3>
            <p className="text-slate-400">Add Boswell as an MCP server to Claude Code.</p>
            <div className="bg-slate-800 rounded-lg p-4 font-mono text-sm text-slate-300 flex items-center justify-between">
              <code>{mcpCommand}</code>
              <button
                onClick={() => copyToClipboard(mcpCommand)}
                className="ml-4 px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs text-slate-300"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <p className="text-slate-500 text-sm">Run this command in your terminal after installing Claude Code.</p>
          </div>
        )}

        {activeTab === 'web' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-100">Claude.ai (Web)</h3>
            <p className="text-slate-400">Connect Boswell to Claude.ai using MCP.</p>
            <div className="p-4 bg-amber-900/20 border border-amber-500/30 rounded-lg">
              <p className="text-amber-400 text-sm">
                Note: MCP support in Claude.ai requires Max, Team, or Enterprise plan.
              </p>
            </div>
            <div className="bg-slate-800 rounded-lg p-4 font-mono text-sm text-slate-300">
              https://delightful-imagination-production-f6a1.up.railway.app/mcp
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

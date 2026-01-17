import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { getApiKeys, createApiKey } from '../lib/api';

interface ApiKey {
  id: string;
  key_prefix: string;
  created_at: string;
}

export default function Connect() {
  const [activeTab, setActiveTab] = useState<'desktop' | 'code' | 'web'>('code');
  const [copied, setCopied] = useState(false);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { token } = useAuth();

  const API_BASE = 'https://delightful-imagination-production-f6a1.up.railway.app';

  useEffect(() => {
    if (token) {
      loadApiKeys();
    }
  }, [token]);

  const loadApiKeys = async () => {
    const data = await getApiKeys();
    if (data.keys) {
      setApiKeys(data.keys);
    }
  };

  const handleCreateKey = async () => {
    setLoading(true);
    const data = await createApiKey();
    if (data.api_key) {
      setNewKey(data.api_key);
      loadApiKeys();
    }
    setLoading(false);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadExtension = () => {
    if (newKey) {
      window.location.href = `${API_BASE}/api/extension/download?api_key=${newKey}`;
    } else {
      alert('Please generate an API key first to download the extension.');
    }
  };

  const mcpCommand = `claude mcp add boswell --url ${API_BASE}/mcp`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-parchment-50">Connect Boswell</h1>
        <p className="text-parchment-200/60 mt-1">Choose how you want to connect Boswell to Claude.</p>
      </div>

      {/* API Key Section */}
      <div className="card rounded-xl p-6">
        <h3 className="text-lg font-semibold text-parchment-50 mb-4">Your API Key</h3>
        {newKey ? (
          <div className="space-y-3">
            <div className="p-4 bg-green-900/20 border border-green-500/30 rounded-lg">
              <p className="text-green-400 text-sm mb-2">New API key created! Save it now - you won't see it again.</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-ink-800 px-3 py-2 rounded text-sm text-parchment-100 font-mono break-all">
                  {newKey}
                </code>
                <button
                  onClick={() => copyToClipboard(newKey)}
                  className="px-3 py-2 bg-ink-700 hover:bg-ink-800 rounded text-xs text-parchment-200"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          </div>
        ) : apiKeys.length > 0 ? (
          <div className="space-y-2">
            {apiKeys.map((key) => (
              <div key={key.id} className="flex items-center justify-between bg-ink-800 px-4 py-2 rounded-lg">
                <code className="text-parchment-200 font-mono">bos_{key.key_prefix}...</code>
                <span className="text-parchment-200/40 text-sm">Created {new Date(key.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-parchment-200/60 text-sm">No API keys yet. Generate one to get started.</p>
        )}
        <button
          onClick={handleCreateKey}
          disabled={loading}
          className="mt-4 px-4 py-2 bg-ember-500 hover:bg-ember-400 disabled:bg-ink-700 text-ink-950 font-medium rounded-lg transition-colors"
        >
          {loading ? 'Generating...' : 'Generate New API Key'}
        </button>
      </div>

      {/* Connection Methods */}
      <div className="flex gap-2 border-b border-parchment-50/10">
        {(['desktop', 'code', 'web'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={'px-4 py-2 text-sm font-medium border-b-2 transition-colors ' +
              (activeTab === tab
                ? 'border-ember-500 text-ember-400'
                : 'border-transparent text-parchment-200/60 hover:text-parchment-100')
            }
          >
            {tab === 'desktop' && 'Desktop Extension'}
            {tab === 'code' && 'Claude Code'}
            {tab === 'web' && 'Claude.ai (Web)'}
          </button>
        ))}
      </div>

      <div className="card rounded-xl p-6">
        {activeTab === 'desktop' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-parchment-50">Desktop Extension</h3>
            <p className="text-parchment-200/60">Download the Boswell extension bundle (.mcpb) for Claude Desktop.</p>
            <ol className="list-decimal list-inside space-y-2 text-parchment-200/60 text-sm">
              <li>Generate an API key above if you haven't already</li>
              <li>Click the download button below</li>
              <li>Double-click the downloaded .mcpb file to install</li>
              <li>Restart Claude Desktop</li>
            </ol>
            <button
              onClick={handleDownloadExtension}
              disabled={!newKey}
              className="px-6 py-3 bg-ember-500 hover:bg-ember-400 disabled:bg-ink-700 disabled:cursor-not-allowed text-ink-950 font-medium rounded-lg transition-colors"
            >
              {newKey ? 'Download Extension (.mcpb)' : 'Generate API Key First'}
            </button>
          </div>
        )}

        {activeTab === 'code' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-parchment-50">Claude Code</h3>
            <p className="text-parchment-200/60">Add Boswell as an MCP server to Claude Code.</p>
            <div className="bg-ink-800 rounded-lg p-4 font-mono text-sm text-parchment-200 flex items-center justify-between">
              <code className="break-all">{mcpCommand}</code>
              <button
                onClick={() => copyToClipboard(mcpCommand)}
                className="ml-4 px-3 py-1 bg-ink-700 hover:bg-ink-800 rounded text-xs text-parchment-200 shrink-0"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <p className="text-parchment-200/40 text-sm">Run this command in your terminal after installing Claude Code.</p>
          </div>
        )}

        {activeTab === 'web' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-parchment-50">Claude.ai (Web)</h3>
            <p className="text-parchment-200/60">Connect Boswell to Claude.ai using MCP.</p>
            <div className="p-4 bg-amber-900/20 border border-amber-500/30 rounded-lg">
              <p className="text-amber-400 text-sm">
                Note: MCP support in Claude.ai requires Max, Team, or Enterprise plan.
              </p>
            </div>
            <div className="bg-ink-800 rounded-lg p-4 font-mono text-sm text-parchment-200">
              {API_BASE}/mcp
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

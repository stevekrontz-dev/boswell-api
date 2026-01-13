import { useAuth } from '../hooks/useAuth';

export default function Dashboard() {
  const { user } = useAuth();

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Header */}
      <div className="text-center md:text-left">
        <h1 className="font-display text-3xl md:text-4xl text-white mb-2">
          Welcome back, <span className="text-ember-500">{user?.name}</span>
        </h1>
        <p className="text-gray-500 font-body">
          Here's an overview of your Boswell usage.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border hover:border-boswell-border-light transition-colors group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-500 text-sm font-medium">Branches</span>
            <div className="w-8 h-8 rounded-full bg-ember-glow flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display font-medium text-white group-hover:text-ember-500 transition-colors">0</div>
        </div>
        
        <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border hover:border-boswell-border-light transition-colors group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-500 text-sm font-medium">Memories</span>
            <div className="w-8 h-8 rounded-full bg-ember-glow flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display font-medium text-white group-hover:text-ember-500 transition-colors">0</div>
        </div>
        
        <div className="bg-boswell-card rounded-2xl p-6 border border-boswell-border hover:border-boswell-border-light transition-colors group">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-500 text-sm font-medium">API Calls (24h)</span>
            <div className="w-8 h-8 rounded-full bg-ember-glow flex items-center justify-center">
              <svg className="w-4 h-4 text-ember-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
          </div>
          <div className="text-4xl font-display font-medium text-white group-hover:text-ember-500 transition-colors">0</div>
        </div>
      </div>

      {/* Getting Started */}
      <div className="bg-boswell-card rounded-2xl p-8 border border-boswell-border">
        <h2 className="font-display text-2xl text-white mb-6">Getting Started</h2>
        <ol className="space-y-5">
          <li className="flex items-start gap-4">
            <span className="flex-shrink-0 w-8 h-8 rounded-full bg-ember-500 text-boswell-bg flex items-center justify-center text-sm font-semibold">1</span>
            <div>
              <p className="text-white font-medium">Connect Boswell to your Claude instance</p>
              <p className="text-gray-500 text-sm mt-1">Configure the MCP server to enable memory</p>
            </div>
          </li>
          <li className="flex items-start gap-4">
            <span className="flex-shrink-0 w-8 h-8 rounded-full bg-boswell-border text-gray-500 flex items-center justify-center text-sm font-semibold">2</span>
            <div>
              <p className="text-gray-400 font-medium">Start a conversation and let Boswell capture memories</p>
              <p className="text-gray-600 text-sm mt-1">Memories are automatically organized by branch</p>
            </div>
          </li>
          <li className="flex items-start gap-4">
            <span className="flex-shrink-0 w-8 h-8 rounded-full bg-boswell-border text-gray-500 flex items-center justify-center text-sm font-semibold">3</span>
            <div>
              <p className="text-gray-400 font-medium">Ask Claude about previous conversations - it remembers!</p>
              <p className="text-gray-600 text-sm mt-1">Your AI now has persistent, contextual memory</p>
            </div>
          </li>
        </ol>
      </div>
    </div>
  );
}

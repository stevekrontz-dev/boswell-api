import { useAuth } from '../hooks/useAuth';

export default function Dashboard() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Welcome back, {user?.name}</h1>
        <p className="text-slate-400 mt-1">Here's an overview of your Boswell usage.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
          <div className="text-slate-400 text-sm font-medium mb-2">Branches</div>
          <div className="text-3xl font-bold text-slate-100">0</div>
        </div>
        <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
          <div className="text-slate-400 text-sm font-medium mb-2">Memories</div>
          <div className="text-3xl font-bold text-slate-100">0</div>
        </div>
        <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
          <div className="text-slate-400 text-sm font-medium mb-2">API Calls (24h)</div>
          <div className="text-3xl font-bold text-slate-100">0</div>
        </div>
      </div>

      <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Getting Started</h2>
        <ol className="space-y-3 text-slate-400">
          <li className="flex items-start gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-orange-500/20 text-orange-400 flex items-center justify-center text-sm font-medium">1</span>
            <span>Connect Boswell to your Claude instance</span>
          </li>
          <li className="flex items-start gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-800 text-slate-500 flex items-center justify-center text-sm font-medium">2</span>
            <span>Start a conversation and let Boswell capture memories</span>
          </li>
          <li className="flex items-start gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-800 text-slate-500 flex items-center justify-center text-sm font-medium">3</span>
            <span>Ask Claude about previous conversations - it remembers!</span>
          </li>
        </ol>
      </div>
    </div>
  );
}

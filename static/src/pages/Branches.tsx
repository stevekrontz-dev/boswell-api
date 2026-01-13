import { useState } from 'react';

interface Branch {
  name: string;
  commits: number;
  lastActivity: string;
}

export default function Branches() {
  const [branches] = useState<Branch[]>([]);
  const [newBranchName, setNewBranchName] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleCreateBranch = async (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: Call API to create branch
    setShowCreateModal(false);
    setNewBranchName('');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Branches</h1>
          <p className="text-slate-400 mt-1">Organize your memories into separate branches.</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-orange-500 hover:bg-orange-400 text-slate-900 font-medium rounded-lg transition-colors"
        >
          New Branch
        </button>
      </div>

      {branches.length === 0 ? (
        <div className="bg-slate-900 rounded-xl p-12 border border-slate-800 text-center">
          <p className="text-slate-400">No branches yet. Create your first branch to get started.</p>
        </div>
      ) : (
        <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-800/50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Name</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Commits</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Last Activity</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {branches.map((branch) => (
                <tr key={branch.name}>
                  <td className="px-4 py-3 text-slate-200 font-mono">{branch.name}</td>
                  <td className="px-4 py-3 text-slate-400">{branch.commits}</td>
                  <td className="px-4 py-3 text-slate-400">{branch.lastActivity}</td>
                  <td className="px-4 py-3">
                    <button className="text-red-400 hover:text-red-300 text-sm">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowCreateModal(false)} />
          <form onSubmit={handleCreateBranch} className="relative bg-slate-900 rounded-xl p-6 w-full max-w-md border border-slate-700">
            <h2 className="text-xl font-bold text-slate-100 mb-4">Create Branch</h2>
            <input
              type="text"
              value={newBranchName}
              onChange={(e) => setNewBranchName(e.target.value)}
              placeholder="Branch name"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-slate-100 focus:outline-none focus:border-orange-500"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-orange-500 hover:bg-orange-400 text-slate-900 font-medium rounded-lg"
              >
                Create
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

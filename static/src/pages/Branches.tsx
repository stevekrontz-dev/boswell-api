import { useState, useEffect } from 'react';
import { getBranches, createBranch, type Branch } from '../lib/api';

export default function Branches() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newBranchName, setNewBranchName] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadBranches();
  }, []);

  const loadBranches = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getBranches();
      setBranches(data.branches || []);
    } catch (err) {
      console.error('Failed to load branches:', err);
      setError('Failed to load branches');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateBranch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBranchName.trim()) return;

    setCreating(true);
    try {
      await createBranch(newBranchName.trim());
      setShowCreateModal(false);
      setNewBranchName('');
      loadBranches(); // Refresh the list
    } catch (err) {
      console.error('Failed to create branch:', err);
    } finally {
      setCreating(false);
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-parchment-200/50">Loading branches...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-parchment-50">Branches</h1>
          <p className="text-parchment-200/60 mt-1">Organize your memories into separate branches.</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-ember-500 hover:bg-ember-400 text-ink-950 font-medium rounded-lg transition-colors"
        >
          New Branch
        </button>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      )}

      {branches.length === 0 ? (
        <div className="card rounded-xl p-12 text-center">
          <p className="text-parchment-200/60">No branches yet. Create your first branch to get started.</p>
        </div>
      ) : (
        <div className="card rounded-xl overflow-hidden">
          <table className="w-full">
            <thead className="bg-ink-800/50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-parchment-200/60">Name</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-parchment-200/60">Commits</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-parchment-200/60">Last Activity</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-parchment-200/60">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-parchment-50/10">
              {branches.map((branch) => (
                <tr key={branch.name} className="hover:bg-ink-800/30 transition-colors">
                  <td className="px-4 py-3 text-parchment-100 font-mono">{branch.name}</td>
                  <td className="px-4 py-3 text-parchment-200/60">{branch.commits || 0}</td>
                  <td className="px-4 py-3 text-parchment-200/60">{formatDate(branch.last_activity)}</td>
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
          <div className="absolute inset-0 bg-black/90 backdrop-blur-sm" onClick={() => !creating && setShowCreateModal(false)} />
          <form onSubmit={handleCreateBranch} className="relative bg-ink-950 rounded-xl p-6 w-full max-w-md border border-parchment-50/10 shadow-2xl">
            <h2 className="font-display text-xl font-bold text-parchment-50 mb-4">Create Branch</h2>
            <input
              type="text"
              value={newBranchName}
              onChange={(e) => setNewBranchName(e.target.value)}
              placeholder="Branch name"
              disabled={creating}
              className="w-full bg-ink-800 border border-parchment-50/10 rounded-lg px-4 py-2 text-parchment-100 focus:outline-none focus:border-ember-500/50 disabled:opacity-50"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                disabled={creating}
                className="px-4 py-2 text-parchment-200/60 hover:text-parchment-100 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating || !newBranchName.trim()}
                className="px-4 py-2 bg-ember-500 hover:bg-ember-400 text-ink-950 font-medium rounded-lg disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

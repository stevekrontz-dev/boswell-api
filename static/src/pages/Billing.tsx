export default function Billing() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Billing</h1>
        <p className="text-slate-400 mt-1">Manage your subscription and usage.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
          <h3 className="text-lg font-semibold text-slate-100 mb-4">Current Plan</h3>
          <div className="flex items-baseline gap-2 mb-4">
            <span className="text-3xl font-bold text-slate-100">Free</span>
            <span className="text-slate-400">$0/month</span>
          </div>
          <ul className="space-y-2 text-slate-400 text-sm mb-6">
            <li>1 branch</li>
            <li>100 memories</li>
            <li>Basic support</li>
          </ul>
          <button className="w-full py-2 bg-orange-500 hover:bg-orange-400 text-slate-900 font-medium rounded-lg transition-colors">
            Upgrade to Pro
          </button>
        </div>

        <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
          <h3 className="text-lg font-semibold text-slate-100 mb-4">Usage This Month</h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-400">Branches</span>
                <span className="text-slate-200">0 / 1</span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full">
                <div className="h-2 bg-orange-500 rounded-full w-0"></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-400">Memories</span>
                <span className="text-slate-200">0 / 100</span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full">
                <div className="h-2 bg-orange-500 rounded-full w-0"></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-400">API Calls</span>
                <span className="text-slate-200">0 / 1,000</span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full">
                <div className="h-2 bg-orange-500 rounded-full w-0"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Enhanced Desktop Extension Section
 * Created by CC4 for CC3 - optional component to replace the desktop tab content
 * Uses copy from DASHBOARD_COPY.md
 */

import { CONNECT_COPY } from './copy';

interface DesktopExtensionSectionProps {
  onDownload: () => void;
  hasApiKey: boolean;
  isLoading?: boolean;
}

export function DesktopExtensionSection({
  onDownload,
  hasApiKey,
  isLoading = false
}: DesktopExtensionSectionProps) {
  const { hero, download, steps, features, requirements } = CONNECT_COPY;

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="text-center py-6">
        <h2 className="text-2xl font-bold text-slate-100">{hero.headline}</h2>
        <p className="text-slate-400 mt-2 text-lg">{hero.subhead}</p>
      </div>

      {/* Download Button */}
      <div className="flex flex-col items-center gap-2">
        <button
          onClick={onDownload}
          disabled={!hasApiKey || isLoading}
          className="px-8 py-4 bg-orange-500 hover:bg-orange-400 disabled:bg-slate-700 disabled:cursor-not-allowed text-slate-900 font-semibold text-lg rounded-xl transition-colors shadow-lg shadow-orange-500/20"
        >
          {isLoading ? 'Preparing...' : hasApiKey ? download.buttonText : 'Generate API Key First'}
        </button>
        {hasApiKey && (
          <span className="text-slate-500 text-sm">{download.buttonSubtext}</span>
        )}
      </div>

      {/* Steps */}
      <div className="py-6">
        <h3 className="text-lg font-semibold text-slate-100 mb-6 text-center">{steps.title}</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {steps.items.map((step, index) => (
            <div key={index} className="flex flex-col items-center text-center p-4 bg-slate-800/50 rounded-xl">
              <div className="w-12 h-12 bg-orange-500/20 rounded-full flex items-center justify-center mb-4">
                <span className="text-orange-400 font-bold text-lg">{index + 1}</span>
              </div>
              <h4 className="font-medium text-slate-100 mb-2">{step.title}</h4>
              <p className="text-slate-400 text-sm">{step.text}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Features */}
      <div className="py-6 border-t border-slate-800">
        <h3 className="text-lg font-semibold text-slate-100 mb-4">{features.title}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {features.items.map((feature, index) => (
            <div key={index} className="flex items-start gap-3 p-3 bg-slate-800/30 rounded-lg">
              <span className="text-orange-400 mt-0.5">&#10003;</span>
              <div>
                <span className="font-medium text-slate-200">{feature.label}</span>
                <span className="text-slate-400"> - {feature.description}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Requirements */}
      <div className="py-4 border-t border-slate-800">
        <h4 className="text-sm font-medium text-slate-400 mb-2">{requirements.title}</h4>
        <div className="flex flex-wrap gap-2">
          {requirements.items.map((req, index) => (
            <span key={index} className="px-3 py-1 bg-slate-800 rounded-full text-xs text-slate-400">
              {req}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export default DesktopExtensionSection;

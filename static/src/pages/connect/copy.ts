/**
 * Dashboard Copy Constants for Connect Page
 * Created by CC4 for CC3 integration
 * Source: extension/docs/DASHBOARD_COPY.md
 */

export const CONNECT_COPY = {
  // Hero Section
  hero: {
    headline: 'Connect Boswell to Claude Desktop',
    subhead: 'Give your AI persistent memory in under 60 seconds.',
  },

  // Download Button
  download: {
    buttonText: 'Download Extension',
    buttonSubtext: 'boswell.mcpb (~4 MB)',
  },

  // Steps Section
  steps: {
    title: 'How it works',
    items: [
      {
        icon: 'download', // Use appropriate icon component
        title: 'Download',
        text: 'Click the button above to get your personalized extension bundle.',
      },
      {
        icon: 'click',
        title: 'Install',
        text: 'Double-click the downloaded file. Claude Desktop handles the rest.',
      },
      {
        icon: 'chat',
        title: 'Start remembering',
        text: 'Say "boswell_startup" in any conversation. You\'re connected!',
      },
    ],
  },

  // Features List
  features: {
    title: 'What you get',
    items: [
      { label: '13 memory tools', description: 'Commit, search, recall, link, and more' },
      { label: 'Cross-conversation context', description: 'Pick up where you left off' },
      { label: 'Knowledge graph', description: 'Build connections across projects' },
      { label: 'Sacred manifest', description: 'Never forget your commitments' },
      { label: 'Instant sync', description: 'Your memories live in the cloud' },
    ],
  },

  // Requirements
  requirements: {
    title: 'Requirements',
    items: [
      'Claude Desktop 1.0.0+',
      'macOS, Windows, or Linux',
      'Active Boswell subscription',
    ],
  },

  // Error Messages
  errors: {
    noApiKey: 'Create an API key to connect Boswell.',
    invalidKey: 'This API key is invalid or expired. Create a new one.',
    networkError: "Can't reach Boswell. Check your connection.",
    notLoggedIn: 'Log in to download your extension.',
    noSubscription: 'Subscribe to download the extension.',
    generationFailed: "Couldn't create your bundle. Try again.",
  },

  // Success Messages
  success: {
    keyCreated: 'API key created. Copy it now!',
    keyRevoked: 'API key revoked successfully.',
    extensionDownloaded: 'Extension ready! Double-click to install.',
    settingsSaved: 'Settings saved.',
  },

  // Empty States
  emptyStates: {
    noApiKeys: {
      title: 'No API keys',
      text: 'Create an API key to authenticate with Boswell.',
      cta: '+ Create Key',
    },
  },

  // Tooltips
  tooltips: {
    apiKey: 'Used to authenticate your Claude Desktop with Boswell',
    tenantId: 'Your unique Boswell account identifier',
    branch: 'A category for organizing memories (like a folder)',
    commit: 'A saved memory with a message and content',
  },
} as const;

// Type for the copy object
export type ConnectCopy = typeof CONNECT_COPY;

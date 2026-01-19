import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWithAuth, getCurrentUser, type UserProfile } from '../lib/api';
import * as d3 from 'd3';

interface Memory {
  id: string;
  fullId: string;
  preview: string;
  content: string;
  type: string;
  branch: string;
  color: string;
  radius: number;
  heat: number;
  normalizedHeat: number;
  memoryType: string;
  createdAt?: string;
}

interface Trail {
  source: string;
  target: string;
  strength: number;
  type: string;
}

interface Link {
  source: string;
  target: string;
  strength: number;
  type: string;
  reasoning?: string;
}

interface BranchConfig {
  color: string;
  label: string;
}

// Default colors for branches - will be augmented dynamically
const BRANCH_COLORS = [
  '#4a6a9a', '#6a5a9a', '#3a8a8a', '#8a4a8a', '#3a8a6a', '#9a7a3a',
  '#7a4a4a', '#4a7a9a', '#9a6a4a', '#5a8a5a', '#8a6a6a', '#6a8a7a'
];

function generateBranchColor(index: number): string {
  return BRANCH_COLORS[index % BRANCH_COLORS.length];
}

function formatBranchLabel(name: string): string {
  return name
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function extractType(preview: string): string {
  const match = (preview || '').match(/"type":\s*"([^"]+)"/);
  if (match) return match[1].replace(/_/g, ' ');
  const colonMatch = (preview || '').match(/^([a-z_]+):/);
  return colonMatch ? colonMatch[1].replace(/_/g, ' ') : 'memory';
}

function getTypeClass(type: string): string {
  if (type.includes('vision') || type.includes('core')) return 'vision';
  if (type.includes('decision') || type.includes('strategic')) return 'decision';
  if (type.includes('fix') || type.includes('resolved')) return 'fix';
  if (type.includes('incident')) return 'incident';
  if (type.includes('spec') || type.includes('infrastructure')) return 'spec';
  if (type.includes('complete') || type.includes('milestone')) return 'complete';
  if (type.includes('insight') || type.includes('lesson')) return 'insight';
  return 'task';
}

// Generate a human-feeling narrative from memory content
function narrateMemory(preview: string): { narrative: string; emotion?: string } {
  if (!preview) return { narrative: 'A moment I wanted to remember.' };

  let data: any = null;

  // Try to parse as JSON - handle cases where braces are missing
  try {
    data = JSON.parse(preview);
  } catch {
    if (preview.includes('"type"') || preview.includes('"title"')) {
      try {
        data = JSON.parse(`{${preview}}`);
      } catch { /* still not valid */ }
    }
  }

  if (!data) {
    // Not JSON at all - return cleaned preview
    const clean = preview.replace(/[{}"]/g, '').trim();
    return { narrative: clean.substring(0, 100) + (clean.length > 100 ? '...' : '') };
  }

  const type = (data.type || '').toLowerCase();

  // Content fields in priority order (what the memory is ABOUT)
  const contentFields = [
    'achievement', 'title', 'decision', 'insight', 'principle', 'lesson',
    'problem', 'solution', 'commitment', 'vision', 'definition', 'spec',
    'action', 'milestone', 'summary', 'message', 'description', 'what',
    'change', 'feature', 'component', 'service', 'finding', 'outcome'
  ];

  // Metadata fields to skip when looking for content
  const metadataFields = [
    'type', 'date', 'timestamp', 'created_at', 'claimed_at', 'updated_at',
    'id', 'task_id', 'worker_id', 'instance_id', 'branch', 'tenant_id',
    'blob_hash', 'commit_hash', 'version'
  ];

  // Find the best content field
  let mainContent = '';
  let secondaryContent = '';

  for (const field of contentFields) {
    if (data[field] && typeof data[field] === 'string' && data[field].length > 3) {
      if (!mainContent) mainContent = data[field];
      else if (!secondaryContent) secondaryContent = data[field];
      else break;
    }
  }

  // If no content fields found, get first non-metadata string field
  if (!mainContent) {
    for (const [key, value] of Object.entries(data)) {
      if (!metadataFields.includes(key) && typeof value === 'string' && value.length > 3) {
        mainContent = value;
        break;
      }
    }
  }

  // Generate prefix based on type
  let prefix = '';
  if (type.includes('lesson') || type.includes('learned')) prefix = 'Learned: ';
  else if (type.includes('decision')) prefix = 'Decided: ';
  else if (type.includes('deploy') || type.includes('ship')) prefix = 'Shipped: ';
  else if (type.includes('milestone') || type.includes('complete')) prefix = 'Milestone: ';
  else if (type.includes('fix') || type.includes('bug')) prefix = 'Fixed: ';
  else if (type.includes('incident') || type.includes('error')) prefix = 'Resolved: ';
  else if (type.includes('commit') || type.includes('promise')) prefix = 'Committed: ';
  else if (type.includes('vision') || type.includes('core')) prefix = '';
  else if (type.includes('spec') || type.includes('design')) prefix = 'Designed: ';
  else if (type.includes('config') || type.includes('setup')) prefix = 'Configured: ';
  else if (type.includes('test') || type.includes('verif')) prefix = 'Tested: ';
  else if (type.includes('swarm') || type.includes('role')) {
    const role = data.role || data.claimed_role || '';
    const worker = data.worker_id || '';
    if (role && worker) return { narrative: `${worker} claimed ${role} role` };
  }
  else if (type.includes('progress') || type.includes('update')) prefix = 'Progress: ';
  else if (type.includes('foundation') || type.includes('init')) prefix = 'Started: ';
  else if (type.includes('debt') || type.includes('todo')) prefix = 'Noted: ';

  // Build narrative
  if (mainContent) {
    const narrative = prefix + mainContent + (secondaryContent ? `. ${secondaryContent}` : '');
    return { narrative: narrative.substring(0, 150), emotion: data.emotional_note };
  }

  // Ultimate fallback - format the type nicely
  const typeLabel = type.replace(/_/g, ' ');
  return { narrative: typeLabel || 'A memory' };
}

// Format timestamp as relative human time
function formatRelativeTime(dateStr: string | undefined): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} week${Math.floor(diffDays / 7) > 1 ? 's' : ''} ago`;
  return date.toLocaleDateString();
}

export default function Mindstate() {
  const navigate = useNavigate();
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const gRef = useRef<d3.Selection<SVGGElement, unknown, null, undefined> | null>(null);
  const nodesRef = useRef<any[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [trails, setTrails] = useState<Trail[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [branches, setBranches] = useState<Record<string, BranchConfig>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [currentBranch, setCurrentBranch] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [showMobilePanel, setShowMobilePanel] = useState(false);
  const [thoughtBubble, setThoughtBubble] = useState<{
    memory: Memory;
    x: number;
    y: number;
    connections: Array<{ memory: Memory; type: string; strength: number; reasoning?: string }>;
  } | null>(null);

  // Check Pro subscription
  useEffect(() => {
    async function checkSubscription() {
      try {
        const user = await getCurrentUser();
        setProfile(user);
        if (user.status !== 'active' || !user.has_subscription) {
          setLoading(false);
        }
      } catch (err) {
        console.error('Failed to check subscription:', err);
        setError('Failed to verify subscription');
        setLoading(false);
      }
    }
    checkSubscription();
  }, []);

  // Fetch branches dynamically
  useEffect(() => {
    if (!profile || profile.status !== 'active' || !profile.has_subscription) return;

    async function fetchBranches() {
      try {
        const data = await fetchWithAuth('/v2/branches');
        const branchConfig: Record<string, BranchConfig> = {};
        (data.branches || []).forEach((b: any, index: number) => {
          branchConfig[b.name] = {
            color: generateBranchColor(index),
            label: formatBranchLabel(b.name)
          };
        });
        setBranches(branchConfig);
      } catch (err) {
        console.error('Failed to load branches:', err);
      }
    }
    fetchBranches();
  }, [profile]);

  // Fetch data from Boswell API (only if Pro and branches loaded)
  useEffect(() => {
    if (!profile || profile.status !== 'active' || !profile.has_subscription) return;
    if (Object.keys(branches).length === 0) return;

    async function fetchData() {
      try {
        const [graphData, trailsData, linksData] = await Promise.all([
          fetchWithAuth('/v2/graph?limit=300'),
          fetchWithAuth('/v2/trails/hot?limit=100'),
          fetchWithAuth('/v2/links?limit=100')
        ]);

        // Calculate heat for each memory
        const heatMap = new Map<string, number>();
        (trailsData.trails || []).forEach((t: any) => {
          const sourceId = t.source_blob.substring(0, 8);
          const targetId = t.target_blob.substring(0, 8);
          heatMap.set(sourceId, (heatMap.get(sourceId) || 0) + (t.strength || 0.5));
          heatMap.set(targetId, (heatMap.get(targetId) || 0) + (t.strength || 0.5));
        });
        (linksData.links || []).forEach((l: any) => {
          const sourceId = l.source_blob.substring(0, 8);
          const targetId = l.target_blob.substring(0, 8);
          heatMap.set(sourceId, (heatMap.get(sourceId) || 0) + (l.weight || 0.3));
          heatMap.set(targetId, (heatMap.get(targetId) || 0) + (l.weight || 0.3));
        });
        const maxHeat = Math.max(...heatMap.values(), 1);

        // Helper to detect branch from content
        function getBranch(preview: string): string {
          const p = (preview || '').toLowerCase();
          // Check for explicit branch mentions first (case-insensitive)
          for (const branchName of Object.keys(branches)) {
            if (p.includes(branchName.toLowerCase())) return branchName;
          }
          // Fallback heuristics
          if (p.includes('square') || p.includes('payment') || p.includes('crm')) return 'tint-atlanta';
          if (p.includes('iris') || p.includes('faculty') || p.includes('research')) return 'iris';
          if (p.includes('franchise') || p.includes('empire')) return 'tint-empire';
          if (p.includes('family') || p.includes('diego') || p.includes('music') || p.includes('personal')) return 'family';
          if (p.includes('mining') || p.includes('crypto') || p.includes('hashrate') || p.includes('xmr')) return 'crypto-mining';
          if (p.includes('infrastructure') || p.includes('mcp') || p.includes('fix') || p.includes('swarm')) return 'command-center';
          return 'boswell';
        }

        // Process memories
        const processedMemories: Memory[] = (graphData.nodes || []).map((node: any) => {
          const id = node.id.substring(0, 8);
          const branch = node.branch || getBranch(node.preview || '');  // Use backend branch, fallback to heuristic
          const branchConfig = branches[branch] || { color: '#666', label: branch };
          const heat = heatMap.get(id) || 0;
          const normalizedHeat = heat / maxHeat;
          return {
            id,
            fullId: node.id,
            preview: node.preview || '',
            content: node.preview || '',
            type: node.type,
            branch,
            color: branchConfig.color,
            radius: 4 + (normalizedHeat * 10),
            heat,
            normalizedHeat,
            memoryType: extractType(node.preview || ''),
            createdAt: node.created_at || node.timestamp
          };
        });

        // Process trails
        const processedTrails: Trail[] = (trailsData.trails || []).map((t: any) => ({
          source: t.source_blob.substring(0, 8),
          target: t.target_blob.substring(0, 8),
          strength: t.strength || 0.5,
          type: 'trail'
        }));

        // Process links
        const processedLinks: Link[] = (linksData.links || []).map((l: any) => ({
          source: l.source_blob.substring(0, 8),
          target: l.target_blob.substring(0, 8),
          strength: l.weight || 0.5,
          type: l.link_type || 'resonance',
          reasoning: l.reasoning
        }));

        setMemories(processedMemories);
        setTrails(processedTrails);
        setLinks(processedLinks);
        setLoading(false);
      } catch (err) {
        console.error('Failed to load Boswell data:', err);
        setError('Failed to load memories');
        setLoading(false);
      }
    }
    fetchData();
  }, [profile, branches]);

  // D3 Visualization
  useEffect(() => {
    if (loading || !svgRef.current || memories.length === 0 || Object.keys(branches).length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    const g = svg.append('g');
    gRef.current = g;

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (e) => g.attr('transform', e.transform));
    svg.call(zoom);
    zoomRef.current = zoom;

    // Build nodes
    const nodes: any[] = [];
    const nodeMap = new Map();

    // Hub nodes from dynamic branches
    Object.entries(branches).forEach(([id, cfg]) => {
      const node = { id: `hub-${id}`, type: 'hub', branch: id, label: cfg.label, color: cfg.color, radius: 22 };
      nodes.push(node);
      nodeMap.set(node.id, node);
    });

    // Memory nodes
    memories.forEach(m => {
      const node = { ...m, type: 'memory' };
      nodes.push(node);
      nodeMap.set(m.id, node);
    });

    // Build links
    const graphLinks: any[] = [];

    // Hub backbone - connect all hubs to boswell as center, plus some cross-connections
    const branchNames = Object.keys(branches);
    const boswellHub = 'hub-boswell';
    branchNames.forEach(name => {
      if (name !== 'boswell') {
        graphLinks.push({ source: boswellHub, target: `hub-${name}`, type: 'backbone' });
      }
    });
    // Some extra backbone connections
    if (branches['command-center'] && branches['iris']) {
      graphLinks.push({ source: 'hub-command-center', target: 'hub-iris', type: 'backbone' });
    }
    if (branches['command-center'] && branches['tint-atlanta']) {
      graphLinks.push({ source: 'hub-command-center', target: 'hub-tint-atlanta', type: 'backbone' });
    }
    if (branches['tint-atlanta'] && branches['tint-empire']) {
      graphLinks.push({ source: 'hub-tint-atlanta', target: 'hub-tint-empire', type: 'backbone' });
    }

    // Hierarchy links
    memories.forEach(m => {
      if (branches[m.branch]) {
        graphLinks.push({ source: `hub-${m.branch}`, target: m.id, type: 'hierarchy' });
      }
    });

    // Trail links
    trails.forEach(t => {
      if (nodeMap.has(t.source) && nodeMap.has(t.target)) {
        graphLinks.push({ source: t.source, target: t.target, type: 'trail', strength: t.strength });
      }
    });

    // Semantic links
    links.forEach(l => {
      if (nodeMap.has(l.source) && nodeMap.has(l.target)) {
        graphLinks.push({ source: l.source, target: l.target, type: 'link', strength: l.strength });
      }
    });

    // Store nodes ref for zoom-to-branch
    nodesRef.current = nodes;

    // Force simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(graphLinks).id((d: any) => d.id)
        .distance((d: any) => d.type === 'backbone' ? 160 : d.type === 'hierarchy' ? 65 : 90)
        .strength((d: any) => d.type === 'backbone' ? 0.7 : d.type === 'hierarchy' ? 0.5 : 0.12))
      .force('charge', d3.forceManyBody().strength((d: any) => d.type === 'hub' ? -350 : -40))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d: any) => d.radius + 8));


    // Draw links
    const link = g.append('g').selectAll('line').data(graphLinks).join('line')
      .attr('stroke', (d: any) => d.type === 'backbone' ? '#2a3a4a' : d.type === 'hierarchy' ? '#1a2530' : d.type === 'link' ? '#5a4a6a' : '#4a6a5a')
      .attr('stroke-width', (d: any) => d.type === 'backbone' ? 1.5 : (d.type === 'trail' || d.type === 'link') ? (d.strength || 0.5) * 2 : 0.8)
      .attr('stroke-opacity', (d: any) => d.type === 'backbone' ? 0.3 : d.type === 'hierarchy' ? 0.15 : 0.4);

    // Draw nodes
    const node = g.append('g').selectAll<SVGGElement, any>('g').data(nodes).join('g')
      .attr('class', 'cursor-pointer')
      .call(d3.drag<SVGGElement, any>()
        .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));

    // Hub glow
    node.filter((d: any) => d.type === 'hub').append('circle')
      .attr('r', (d: any) => d.radius + 8)
      .attr('fill', (d: any) => d.color)
      .attr('fill-opacity', 0.06);

    // Hot memory glow
    node.filter((d: any) => d.type === 'memory' && d.normalizedHeat > 0.3).append('circle')
      .attr('r', (d: any) => d.radius + 4 + (d.normalizedHeat * 6))
      .attr('fill', (d: any) => d.color)
      .attr('fill-opacity', (d: any) => d.normalizedHeat * 0.15);

    // Main circles
    node.append('circle')
      .attr('r', (d: any) => d.radius)
      .attr('fill', (d: any) => d.color)
      .attr('fill-opacity', (d: any) => d.type === 'hub' ? 0.7 : 0.35 + (d.normalizedHeat || 0) * 0.5)
      .attr('stroke', (d: any) => d.color)
      .attr('stroke-width', (d: any) => d.type === 'hub' ? 1.5 : 1 + (d.normalizedHeat || 0) * 1.5)
      .attr('stroke-opacity', (d: any) => d.type === 'hub' ? 0.6 : 0.4 + (d.normalizedHeat || 0) * 0.4);

    // Hub labels
    node.filter((d: any) => d.type === 'hub').append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', (d: any) => d.radius + 16)
      .attr('fill', (d: any) => d.color)
      .attr('fill-opacity', 0.6)
      .attr('font-size', '9px')
      .attr('font-weight', '400')
      .attr('letter-spacing', '1px')
      .text((d: any) => d.label.toUpperCase());

    // Click handler - use event coordinates for bubble positioning
    node.on('click', (event: any, d: any) => {
      if (d.type === 'memory') {
        setSelectedMemory(d);

        const connections: Array<{ memory: Memory; type: string; strength: number; reasoning?: string }> = [];
        const memoryMap = new Map(memories.map(m => [m.id, m]));

        trails.forEach(t => {
          if (t.source === d.id && memoryMap.has(t.target)) {
            connections.push({ memory: memoryMap.get(t.target)!, type: 'trail', strength: t.strength });
          } else if (t.target === d.id && memoryMap.has(t.source)) {
            connections.push({ memory: memoryMap.get(t.source)!, type: 'trail', strength: t.strength });
          }
        });

        links.forEach(l => {
          if (l.source === d.id && memoryMap.has(l.target)) {
            connections.push({ memory: memoryMap.get(l.target)!, type: l.type, strength: l.strength, reasoning: l.reasoning });
          } else if (l.target === d.id && memoryMap.has(l.source)) {
            connections.push({ memory: memoryMap.get(l.source)!, type: l.type, strength: l.strength, reasoning: l.reasoning });
          }
        });

        connections.sort((a, b) => b.strength - a.strength);

        // Get click position relative to graph panel
        const svgRect = svgRef.current?.getBoundingClientRect();
        const clickX = event.clientX - (svgRect?.left || 0);
        const clickY = event.clientY - (svgRect?.top || 0);

        setThoughtBubble({
          memory: d,
          x: clickX,
          y: clickY,
          connections: connections.slice(0, 8)
        });
      } else if (d.type === 'hub') {
        setCurrentBranch(d.branch);
        setThoughtBubble(null);
      }
    });

    svg.on('click', (e: any) => {
      if (e.target === svgRef.current) {
        setThoughtBubble(null);
      }
    });

    simulation.on('tick', () => {
      link.attr('x1', (d: any) => d.source.x).attr('y1', (d: any) => d.source.y)
          .attr('x2', (d: any) => d.target.x).attr('y2', (d: any) => d.target.y);
      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

  }, [loading, memories, trails, links, branches]);

  // Zoom to branch when selected
  useEffect(() => {
    if (currentBranch === 'all' || !svgRef.current || !zoomRef.current || !gRef.current || nodesRef.current.length === 0) return;

    const svg = d3.select(svgRef.current);
    const zoom = zoomRef.current;
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    // Find nodes belonging to this branch (including the hub)
    const branchNodes = nodesRef.current.filter((n: any) =>
      n.branch === currentBranch || n.id === `hub-${currentBranch}`
    );

    if (branchNodes.length === 0) return;

    // Calculate bounding box
    const xs = branchNodes.map((n: any) => n.x).filter((x: any) => x !== undefined);
    const ys = branchNodes.map((n: any) => n.y).filter((y: any) => y !== undefined);

    if (xs.length === 0 || ys.length === 0) return;

    const minX = Math.min(...xs) - 50;
    const maxX = Math.max(...xs) + 50;
    const minY = Math.min(...ys) - 50;
    const maxY = Math.max(...ys) + 50;

    const boxWidth = maxX - minX;
    const boxHeight = maxY - minY;

    // Calculate transform to fit branch in view
    const scale = Math.min(width / boxWidth, height / boxHeight, 2) * 0.85;
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    const transform = d3.zoomIdentity
      .translate(width / 2, height / 2)
      .scale(scale)
      .translate(-centerX, -centerY);

    svg.transition().duration(750).call(zoom.transform, transform);
  }, [currentBranch]);


  const filteredMemories = memories.filter(m => {
    const matchBranch = currentBranch === 'all' || m.branch === currentBranch;
    const matchSearch = !searchTerm ||
      m.preview.toLowerCase().includes(searchTerm.toLowerCase()) ||
      m.content.toLowerCase().includes(searchTerm.toLowerCase());
    return matchBranch && matchSearch;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-400">Loading Boswell Connectome...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">{error}</div>
      </div>
    );
  }

  if (profile && (profile.status !== 'active' || !profile.has_subscription)) {
    return (
      <div className="flex items-center justify-center h-full bg-[#0c0c10] p-4">
        <div className="text-center max-w-md">
          <div className="text-6xl mb-6">🍄</div>
          <h2 className="text-2xl font-serif text-gray-200 mb-4">Boswell Connectome</h2>
          <p className="text-gray-500 mb-6">
            Visualize your memory network with our Physarum-inspired neural map.
            See how your thoughts connect, which memories are most active, and explore
            the semantic trails between ideas.
          </p>
          <p className="text-gray-600 text-sm mb-8">
            This feature is available exclusively for Pro subscribers.
          </p>
          <button
            onClick={() => navigate('/dashboard/billing')}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
          >
            Upgrade to Pro
          </button>
        </div>
      </div>
    );
  }

  const branchCount = Object.keys(branches).length;

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-3.5rem)] md:h-[calc(100vh-4rem)] bg-[#0c0c10] overflow-hidden">
      {/* Graph Panel */}
      <div className="flex-1 relative min-h-[50vh] md:min-h-0">
        <svg ref={svgRef} className="w-full h-full touch-none" />

        {/* Stats overlay */}
        <div className="absolute top-4 left-4 md:top-6 md:left-6 bg-[#0c0c10]/90 backdrop-blur-sm border border-gray-700/30 rounded-lg p-3 md:p-4 text-xs text-gray-500">
          <h2 className="text-gray-300 text-sm md:text-base font-serif mb-2 md:mb-3">Boswell Connectome</h2>
          <div className="space-y-1 md:space-y-2">
            <div className="flex justify-between gap-4 md:gap-8"><span>Branches</span> <span className="text-gray-400">{branchCount}</span></div>
            <div className="flex justify-between gap-4 md:gap-8"><span>Memories</span> <span className="text-gray-400">{memories.length}</span></div>
            <div className="flex justify-between gap-4 md:gap-8"><span>Connections</span> <span className="text-gray-400">{trails.length + links.length}</span></div>
          </div>
        </div>

        {/* Legend - hidden on mobile */}
        <div className="absolute bottom-6 left-6 bg-[#0c0c10]/90 backdrop-blur-sm border border-gray-700/30 rounded-lg p-4 text-xs hidden lg:block">
          <div className="text-gray-600 uppercase tracking-wider text-[10px] mb-2">Branches</div>
          {Object.entries(branches).map(([id, cfg]) => (
            <div key={id} className="flex items-center gap-2 text-gray-500 my-1">
              <div className="w-2 h-2 rounded-full" style={{ background: cfg.color }} />
              {cfg.label}
            </div>
          ))}
        </div>

        {/* Mobile toggle button */}
        <button
          onClick={() => setShowMobilePanel(!showMobilePanel)}
          className="md:hidden absolute bottom-4 right-4 bg-[#14141c] border border-gray-700/30 rounded-full p-3 text-gray-400"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={showMobilePanel ? "M6 18L18 6M6 6l12 12" : "M4 6h16M4 12h16M4 18h16"} />
          </svg>
        </button>

        {/* Thought Bubble - positioned relative to node */}
        {thoughtBubble && (() => {
          // Calculate bubble position - float above the node
          const bubbleWidth = 320;
          const bubbleHeight = 140;
          const padding = 20;
          const tailLength = 50;

          // Get graph container bounds (approximate)
          const graphWidth = window.innerWidth - 384; // minus sidebar
          const graphHeight = window.innerHeight - 64; // minus nav

          // Position bubble above node, keep within bounds
          let bubbleX = thoughtBubble.x - bubbleWidth / 2;
          let bubbleY = thoughtBubble.y - bubbleHeight - tailLength;

          // Clamp to viewport
          bubbleX = Math.max(padding, Math.min(bubbleX, graphWidth - bubbleWidth - padding));
          bubbleY = Math.max(padding, Math.min(bubbleY, graphHeight - bubbleHeight - padding));

          // If bubble would be above viewport, put it below the node
          const bubbleBelow = thoughtBubble.y < bubbleHeight + tailLength + 60;
          if (bubbleBelow) {
            bubbleY = thoughtBubble.y + tailLength;
          }

          // Calculate tail position to point at node
          const tailX = Math.max(30, Math.min(thoughtBubble.x - bubbleX, bubbleWidth - 30));

          return (
            <div
              className="absolute z-50 transition-all duration-200"
              style={{ left: bubbleX, top: bubbleY }}
            >
              {/* Main bubble */}
              <div
                className="relative bg-[#1a1a24] border border-gray-500/30 rounded-[1.5rem] p-5 shadow-2xl"
                style={{
                  width: bubbleWidth,
                  boxShadow: '0 0 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)'
                }}
              >
                <button
                  onClick={() => setThoughtBubble(null)}
                  className="absolute top-3 right-3 text-gray-500 hover:text-gray-300 text-lg leading-none p-1"
                >
                  ×
                </button>

                <div className="pr-6">
                  {(() => {
                    const { narrative, emotion } = narrateMemory(thoughtBubble.memory.preview);
                    return (
                      <>
                        <div className="text-gray-200 text-sm leading-relaxed mb-2 font-light italic">
                          "{narrative}"
                        </div>
                        {emotion && (
                          <div className="text-gray-400 text-xs mb-2">
                            — {emotion}
                          </div>
                        )}
                        <div className="text-gray-500 text-xs flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded-full text-[9px] uppercase tracking-wider"
                            style={{ background: `${thoughtBubble.memory.color}30`, color: thoughtBubble.memory.color }}>
                            {thoughtBubble.memory.memoryType}
                          </span>
                          <span>{formatRelativeTime(thoughtBubble.memory.createdAt)}</span>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>

              {/* Thought bubble tail - points toward node */}
              <div
                className={`absolute flex items-center gap-1 ${bubbleBelow ? '-top-6 flex-col-reverse' : '-bottom-6 flex-col'}`}
                style={{ left: tailX, transform: 'translateX(-50%)' }}
              >
                <div className="w-3.5 h-3.5 rounded-full bg-[#1a1a24] border border-gray-500/30" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#1a1a24] border border-gray-500/30" />
                <div className="w-1.5 h-1.5 rounded-full bg-[#1a1a24] border border-gray-500/30" />
              </div>
            </div>
          );
        })()}
      </div>

      {/* Memory Panel - slides up on mobile */}
      <div className={`
        ${showMobilePanel ? 'translate-y-0' : 'translate-y-full md:translate-y-0'}
        fixed md:relative bottom-0 left-0 right-0 md:bottom-auto
        w-full md:w-96 h-[70vh] md:h-auto
        bg-[#0f0f14] border-t md:border-t-0 md:border-l border-gray-700/20 
        flex flex-col transition-transform duration-300 ease-in-out z-40
      `}>
        {/* Mobile drag handle */}
        <div className="md:hidden flex justify-center py-2">
          <div className="w-12 h-1 bg-gray-600 rounded-full" />
        </div>

        {/* Header */}
        <div className="p-4 md:p-5 border-b border-gray-700/20">
          <h3 className="text-gray-400 font-serif mb-3">Memory Timeline</h3>
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setCurrentBranch('all')}
              className={`px-3 py-1 rounded-full text-[10px] border transition-all ${
                currentBranch === 'all'
                  ? 'border-gray-500 text-gray-400 bg-gray-500/10'
                  : 'border-gray-700/30 text-gray-600 hover:border-gray-600'
              }`}
            >
              all
            </button>
            {Object.entries(branches).map(([id, cfg]) => (
              <button
                key={id}
                onClick={() => setCurrentBranch(id)}
                className={`px-3 py-1 rounded-full text-[10px] border transition-all ${
                  currentBranch === id
                    ? 'bg-opacity-10'
                    : 'border-gray-700/30 text-gray-600 hover:border-gray-600'
                }`}
                style={currentBranch === id ? { borderColor: cfg.color, color: cfg.color, backgroundColor: `${cfg.color}20` } : {}}
              >
                {cfg.label}
              </button>
            ))}
          </div>
        </div>

        {/* Search */}
        <div className="px-4 md:px-5 py-3 border-b border-gray-700/20">
          <input
            type="text"
            placeholder="Search memories..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#14141c] border border-gray-700/20 rounded px-3 py-2 text-gray-400 text-xs placeholder-gray-600 focus:outline-none focus:border-gray-600"
          />
        </div>

        {/* Timeline */}
        <div className="flex-1 overflow-y-auto">
          {filteredMemories.map(m => (
            <div
              key={m.id}
              onClick={() => setSelectedMemory(m)}
              className={`grid grid-cols-[40px_1fr] px-4 py-3 cursor-pointer transition-colors ${
                selectedMemory?.id === m.id ? 'bg-blue-500/10' : 'hover:bg-gray-500/5 active:bg-gray-500/10'
              }`}
            >
              <div className="flex flex-col items-center relative">
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-px h-full bg-gray-700/20" />
                <div className="w-2 h-2 rounded-full z-10" style={{ background: m.color }} />
              </div>
              <div className="pl-2">
                <div className="text-[11px] text-gray-500 mb-1">
                  <span className={`inline-block text-[8px] uppercase tracking-wider px-1.5 py-0.5 rounded mr-2 type-${getTypeClass(m.memoryType)}`}
                    style={{ background: `${m.color}30`, color: m.color }}>
                    {m.memoryType}
                  </span>
                  {narrateMemory(m.preview).narrative.substring(0, 70)}
                </div>
                <div className="text-[9px] text-gray-600 flex gap-3">
                  <span className="font-mono text-blue-400/60">{m.id}</span>
                  <span className="text-green-400/50">{branches[m.branch]?.label || m.branch}</span>
                  {m.createdAt && <span className="text-gray-600">{formatRelativeTime(m.createdAt)}</span>}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Detail drawer */}
        {selectedMemory && (
          <div className="border-t border-gray-700/20 bg-[#08080c] max-h-72 overflow-hidden">
            <div className="px-4 md:px-5 py-3 flex justify-between items-center border-b border-gray-700/10">
              <h4 className="text-gray-500 font-serif text-sm">Memory Content</h4>
              <button onClick={() => setSelectedMemory(null)} className="text-gray-600 hover:text-gray-400 p-1">×</button>
            </div>
            <div className="p-4 overflow-y-auto max-h-52">
              <pre className="bg-[#101016] border border-gray-700/10 rounded p-3 text-[10px] text-gray-500 whitespace-pre-wrap break-words">
                {selectedMemory.content}
              </pre>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-4 md:px-5 py-3 border-t border-gray-700/20 text-[9px] text-gray-600 flex justify-between">
          <span>{filteredMemories.length} memories</span>
          <span>{trails.length + links.length} connections</span>
        </div>
      </div>
    </div>
  );
}

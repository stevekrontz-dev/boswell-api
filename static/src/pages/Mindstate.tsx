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

const BRANCHES: Record<string, { color: string; label: string }> = {
  'boswell': { color: '#4a6a9a', label: 'Boswell' },
  'command-center': { color: '#6a5a9a', label: 'Command' },
  'tint-atlanta': { color: '#3a8a8a', label: 'Tint ATL' },
  'iris': { color: '#8a4a8a', label: 'IRIS' },
  'tint-empire': { color: '#3a8a6a', label: 'Empire' },
  'family': { color: '#9a7a3a', label: 'Family' }
};

function getBranch(preview: string): string {
  const p = (preview || '').toLowerCase();
  if (p.includes('square') || p.includes('payment') || p.includes('crm') || p.includes('tint-atlanta')) return 'tint-atlanta';
  if (p.includes('iris') || p.includes('faculty') || p.includes('research')) return 'iris';
  if (p.includes('franchise') || p.includes('empire')) return 'tint-empire';
  if (p.includes('family') || p.includes('diego') || p.includes('music') || p.includes('personal')) return 'family';
  if (p.includes('infrastructure') || p.includes('thalamus') || p.includes('mcp') || p.includes('fix') || p.includes('swarm')) return 'command-center';
  return 'boswell';
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

export default function Mindstate() {
  const navigate = useNavigate();
  const svgRef = useRef<SVGSVGElement>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [trails, setTrails] = useState<Trail[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [currentBranch, setCurrentBranch] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');

  // Check Pro subscription
  useEffect(() => {
    async function checkSubscription() {
      try {
        const user = await getCurrentUser();
        setProfile(user);
        if (user.status !== 'active' || !user.has_subscription) {
          // Not a Pro user - will show upgrade prompt
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

  // Fetch data from Boswell API (only if Pro)
  useEffect(() => {
    if (!profile || profile.status !== 'active' || !profile.has_subscription) return;

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

        // Process memories
        const processedMemories: Memory[] = (graphData.nodes || []).map((node: any) => {
          const id = node.id.substring(0, 8);
          const branch = getBranch(node.preview || '');
          const heat = heatMap.get(id) || 0;
          const normalizedHeat = heat / maxHeat;
          return {
            id,
            fullId: node.id,
            preview: node.preview || '',
            content: node.preview || '',
            type: node.type,
            branch,
            color: BRANCHES[branch].color,
            radius: 4 + (normalizedHeat * 10),
            heat,
            normalizedHeat,
            memoryType: extractType(node.preview || '')
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
  }, [profile]);

  // D3 Visualization
  useEffect(() => {
    if (loading || !svgRef.current || memories.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    const g = svg.append('g');

    // Zoom
    svg.call(d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (e) => g.attr('transform', e.transform)));

    // Build nodes
    const nodes: any[] = [];
    const nodeMap = new Map();

    // Hub nodes
    Object.entries(BRANCHES).forEach(([id, cfg]) => {
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

    // Hub backbone
    [['hub-boswell','hub-command-center'],['hub-boswell','hub-iris'],['hub-boswell','hub-tint-atlanta'],
     ['hub-boswell','hub-tint-empire'],['hub-boswell','hub-family'],['hub-command-center','hub-iris'],
     ['hub-command-center','hub-tint-atlanta'],['hub-tint-atlanta','hub-tint-empire']].forEach(([s,t]) => {
      graphLinks.push({ source: s, target: t, type: 'backbone' });
    });

    // Hierarchy links
    memories.forEach(m => {
      graphLinks.push({ source: `hub-${m.branch}`, target: m.id, type: 'hierarchy' });
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

    // Click handler
    node.on('click', (_e: any, d: any) => {
      if (d.type === 'memory') {
        setSelectedMemory(d);
      } else if (d.type === 'hub') {
        setCurrentBranch(d.branch);
      }
    });

    // Tick
    simulation.on('tick', () => {
      link.attr('x1', (d: any) => d.source.x).attr('y1', (d: any) => d.source.y)
          .attr('x2', (d: any) => d.target.x).attr('y2', (d: any) => d.target.y);
      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

  }, [loading, memories, trails, links]);

  // Filter memories for timeline
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

  // Pro upgrade prompt
  if (profile && (profile.status !== 'active' || !profile.has_subscription)) {
    return (
      <div className="flex items-center justify-center h-full bg-[#0c0c10]">
        <div className="text-center max-w-md p-8">
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

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-[#0c0c10]">
      {/* Graph Panel */}
      <div className="flex-1 relative">
        <svg ref={svgRef} className="w-full h-full" />

        {/* Stats overlay */}
        <div className="absolute top-6 left-6 bg-[#0c0c10]/90 backdrop-blur-sm border border-gray-700/30 rounded-lg p-4 text-xs text-gray-500">
          <h2 className="text-gray-300 text-base font-serif mb-3">Boswell Connectome</h2>
          <div className="space-y-2">
            <div className="flex justify-between gap-8"><span>Branches</span> <span className="text-gray-400">6</span></div>
            <div className="flex justify-between gap-8"><span>Memories</span> <span className="text-gray-400">{memories.length}</span></div>
            <div className="flex justify-between gap-8"><span>Connections</span> <span className="text-gray-400">{trails.length + links.length}</span></div>
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-6 left-6 bg-[#0c0c10]/90 backdrop-blur-sm border border-gray-700/30 rounded-lg p-4 text-xs hidden md:block">
          <div className="text-gray-600 uppercase tracking-wider text-[10px] mb-2">Branches</div>
          {Object.entries(BRANCHES).map(([id, cfg]) => (
            <div key={id} className="flex items-center gap-2 text-gray-500 my-1">
              <div className="w-2 h-2 rounded-full" style={{ background: cfg.color }} />
              {cfg.label}
            </div>
          ))}
        </div>
      </div>

      {/* Memory Panel */}
      <div className="w-96 bg-[#0f0f14] border-l border-gray-700/20 flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-gray-700/20">
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
            {Object.entries(BRANCHES).map(([id, cfg]) => (
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
        <div className="px-5 py-3 border-b border-gray-700/20">
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
                selectedMemory?.id === m.id ? 'bg-blue-500/10' : 'hover:bg-gray-500/5'
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
                  {m.preview.split(': ').slice(1).join(': ').substring(0, 60) || m.preview.substring(0, 60)}
                </div>
                <div className="text-[9px] text-gray-600 flex gap-3">
                  <span className="font-mono text-blue-400/60">{m.id}</span>
                  <span className="text-green-400/50">{BRANCHES[m.branch].label}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Detail drawer */}
        {selectedMemory && (
          <div className="border-t border-gray-700/20 bg-[#08080c] max-h-72 overflow-hidden">
            <div className="px-5 py-3 flex justify-between items-center border-b border-gray-700/10">
              <h4 className="text-gray-500 font-serif text-sm">Memory Content</h4>
              <button onClick={() => setSelectedMemory(null)} className="text-gray-600 hover:text-gray-400">×</button>
            </div>
            <div className="p-4 overflow-y-auto max-h-52">
              <pre className="bg-[#101016] border border-gray-700/10 rounded p-3 text-[10px] text-gray-500 whitespace-pre-wrap">
                {selectedMemory.content}
              </pre>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-700/20 text-[9px] text-gray-600 flex justify-between">
          <span>{filteredMemories.length} memories</span>
          <span>{trails.length + links.length} connections</span>
        </div>
      </div>
    </div>
  );
}

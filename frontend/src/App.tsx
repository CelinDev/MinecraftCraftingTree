import React, { useState, useEffect } from 'react';
import { Search, History, Target, Cpu, Layers, AlertTriangle, CheckCircle, ChevronRight, RefreshCw, Hammer } from 'lucide-react';
import type { CraftingTreeResult, Recipe, CraftingGoal, SearchItem } from './types';
import { formatItemName, formatModName } from './utils';
import { GraphView } from './components/GraphView';

const API_BASE = '/api';

export const App: React.FC = () => {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchItem[]>([]);
  const [recentItems, setRecentItems] = useState<string[]>([]);
  const [selectedItem, setSelectedItem] = useState<string>('kubejs:infinity_1');
  const [targetCount, setTargetCount] = useState<number>(1);
  const [treeResult, setTreeResult] = useState<CraftingTreeResult | null>(null);
  const [itemRecipes, setItemRecipes] = useState<Recipe[]>([]);
  const [selectedRecipesMap, setSelectedRecipesMap] = useState<Record<string, string>>({});
  const [goals, setGoals] = useState<CraftingGoal[]>([]);
  const [activeTab, setActiveTab] = useState<'graph' | 'steps' | 'materials' | 'recipes' | 'goals'>('graph');
  const [pruneBasic, setPruneBasic] = useState<boolean>(true);
  const [avoidMystical, setAvoidMystical] = useState<boolean>(true);
  const [, setLoading] = useState(false);
  const [statusInfo, setStatusInfo] = useState<any>(null);

  useEffect(() => {
    fetch(`${API_BASE}/status`)
      .then((r) => r.json())
      .then(setStatusInfo)
      .catch(() => {});
    fetchRecent();
    fetchGoals();
  }, []);

  useEffect(() => {
    if (selectedItem) {
      loadTree(selectedItem, targetCount, selectedRecipesMap, pruneBasic, avoidMystical);
      loadRecipes(selectedItem);
    }
  }, [selectedItem, targetCount, pruneBasic, avoidMystical]);

  function fetchRecent() {
    fetch(`${API_BASE}/recent`)
      .then((r) => r.json())
      .then(setRecentItems)
      .catch(() => {});
  }

  function fetchGoals() {
    fetch(`${API_BASE}/goals`)
      .then((r) => r.json())
      .then(setGoals)
      .catch(() => {});
  }

  function handleSearch(q: string) {
    setQuery(q);
    if (q.trim().length > 1) {
      fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`)
        .then((r) => r.json())
        .then(setSearchResults)
        .catch(() => {});
    } else {
      setSearchResults([]);
    }
  }

  function loadTree(
    itemKey: string,
    count: number,
    recipeOverrides: Record<string, string>,
    prune: boolean = pruneBasic,
    avoidMa: boolean = avoidMystical,
  ) {
    setLoading(true);
    fetch(`${API_BASE}/crafting-tree`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_key: itemKey,
        count,
        selected_recipes: recipeOverrides,
        prune_basic_resources: prune,
        avoid_mystical_agriculture: avoidMa,
      }),
    })
      .then((r) => r.json())
      .then((data) => {
        setTreeResult(data);
        setLoading(false);
        fetchRecent();
      })
      .catch(() => setLoading(false));
  }

  function loadRecipes(itemKey: string) {
    fetch(`${API_BASE}/items/${encodeURIComponent(itemKey)}/recipes`)
      .then((r) => r.json())
      .then(setItemRecipes)
      .catch(() => {});
  }

  function selectAlternativeRecipe(itemKey: string, recipeId: string) {
    const nextMap = { ...selectedRecipesMap, [itemKey]: recipeId };
    setSelectedRecipesMap(nextMap);
    loadTree(selectedItem, targetCount, nextMap, pruneBasic, avoidMystical);
  }

  function saveAsGoal() {
    if (!selectedItem) return;
    const goalId = `goal_${Date.now()}`;
    const title = `Produzir ${targetCount}x ${treeResult?.target_display_name || formatItemName(selectedItem)}`;
    fetch(`${API_BASE}/goals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        goal_id: goalId,
        title,
        target_item_key: selectedItem,
        target_count: targetCount,
      }),
    })
      .then((r) => r.json())
      .then(() => fetchGoals());
  }

  function toggleGoalStep(goalId: string, stepId: string) {
    fetch(`${API_BASE}/goals/${goalId}/toggle-step/${encodeURIComponent(stepId)}`, {
      method: 'POST',
    })
      .then((r) => r.json())
      .then(() => fetchGoals());
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: '#090d16', color: '#f1f5f9', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* Header */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 28px', backgroundColor: '#0f172a', borderBottom: '1px solid #1e293b' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Hammer color="#38bdf8" size={28} />
          <div>
            <h1 style={{ margin: 0, fontSize: '20px', fontWeight: 'bold', background: 'linear-gradient(to right, #38bdf8, #818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Minecraft Crafting Explorer
            </h1>
            <span style={{ fontSize: '12px', color: '#64748b' }}>
              Project Infinity 0.1 • {statusInfo?.active_recipes_count || '32.956'} receitas ativas carregadas
            </span>
          </div>
        </div>

        {/* Global Search Bar */}
        <div style={{ position: 'relative', width: '440px' }}>
          <div style={{ display: 'flex', alignItems: 'center', backgroundColor: '#1e293b', borderRadius: '8px', padding: '6px 12px', border: '1px solid #334155' }}>
            <Search size={18} color="#94a3b8" />
            <input
              type="text"
              placeholder="Buscar por nome ou ID (ex: Blazing Crystal, iron_ingot)..."
              value={query}
              onChange={(e) => handleSearch(e.target.value)}
              style={{ backgroundColor: 'transparent', border: 'none', color: '#f8fafc', marginLeft: '8px', width: '100%', outline: 'none', fontSize: '13px' }}
            />
          </div>

          {/* Autocomplete Dropdown */}
          {searchResults.length > 0 && (
            <div style={{ position: 'absolute', top: '44px', left: 0, width: '100%', maxHeight: '340px', overflowY: 'auto', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', zIndex: 100, boxShadow: '0 10px 15px -3px rgba(0,0,0,0.5)' }}>
              {searchResults.map((item) => (
                <div
                  key={item.item_id}
                  onClick={() => {
                    setSelectedItem(item.item_id);
                    setSearchResults([]);
                    setQuery('');
                  }}
                  style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#334155')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <img
                      src={`${API_BASE}/items/${encodeURIComponent(item.item_id)}/icon`}
                      alt=""
                      style={{ width: '22px', height: '22px', imageRendering: 'pixelated', objectFit: 'contain' }}
                      onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                    />
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                        {item.display_name || formatItemName(item.item_id)}
                      </div>
                      <div style={{ fontSize: '10px', color: '#94a3b8' }}>
                        {item.item_id} <span style={{ color: '#475569' }}>•</span> <span style={{ color: '#38bdf8' }}>{item.mod_name || item.source_mod}</span>
                      </div>
                    </div>
                  </div>
                  <span style={{ fontSize: '11px', color: '#38bdf8', backgroundColor: '#0369a122', padding: '2px 8px', borderRadius: '4px', border: '1px solid #0284c733' }}>
                    {item.recipes_count} {item.recipes_count === 1 ? 'receita' : 'receitas'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* Main Layout */}
      <div style={{ display: 'flex', flex: 1 }}>
        {/* Sidebar: Recents & Navigation */}
        <aside style={{ width: '260px', backgroundColor: '#0b1120', borderRight: '1px solid #1e293b', padding: '20px 16px' }}>
          <div style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em', marginBottom: '12px' }}>
              <History size={16} /> Consultas Recentes
            </div>
            {recentItems.length === 0 ? (
              <span style={{ fontSize: '12px', color: '#475569' }}>Nenhum item recente</span>
            ) : (
              recentItems.map((item) => (
                <div
                  key={item}
                  onClick={() => setSelectedItem(item)}
                  style={{
                    padding: '6px 10px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    color: selectedItem === item ? '#38bdf8' : '#cbd5e1',
                    backgroundColor: selectedItem === item ? '#1e293b' : 'transparent',
                    marginBottom: '4px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                  title={item}
                >
                  <img
                    src={`${API_BASE}/items/${encodeURIComponent(item)}/icon`}
                    alt=""
                    style={{ width: '16px', height: '16px', imageRendering: 'pixelated', objectFit: 'contain' }}
                    onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                  />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {formatItemName(item)}
                  </span>
                </div>
              ))
            )}
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em', marginBottom: '12px' }}>
              <Target size={16} /> Objetivos Salvos ({goals.length})
            </div>
            {goals.map((g) => (
              <div
                key={g.goal_id}
                onClick={() => {
                  setSelectedItem(g.target_item_key);
                  setTargetCount(g.target_count);
                  setActiveTab('goals');
                }}
                style={{ padding: '8px 10px', backgroundColor: '#131e33', borderRadius: '6px', marginBottom: '8px', cursor: 'pointer', border: '1px solid #1e293b' }}
              >
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#e2e8f0' }}>{g.title}</div>
                <div style={{ fontSize: '11px', color: '#10b981', marginTop: '4px' }}>
                  {g.completed_steps.length} etapas concluídas
                </div>
              </div>
            ))}
          </div>
        </aside>

        {/* Content Area */}
        <main style={{ flex: 1, padding: '24px 32px', overflowY: 'auto' }}>
          {/* Target Controls Banner */}
          <div style={{ backgroundColor: '#131e33', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div style={{ width: '44px', height: '44px', backgroundColor: '#0b1120', border: '1px solid #334155', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <img
                  src={`${API_BASE}/items/${encodeURIComponent(selectedItem)}/icon`}
                  alt=""
                  style={{ width: '32px', height: '32px', imageRendering: 'pixelated', objectFit: 'contain' }}
                  onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                />
              </div>
              <div>
                <div style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {treeResult?.target_mod_name || formatModName(selectedItem.split(':')[0])}
                </div>
                <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#f8fafc' }}>
                  {treeResult?.target_display_name || formatItemName(selectedItem)}
                </div>
                <div style={{ fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                  {selectedItem}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                  backgroundColor: pruneBasic ? '#0f766e22' : '#1e293b',
                  border: `1px solid ${pruneBasic ? '#14b8a6' : '#334155'}`,
                  padding: '6px 14px',
                  borderRadius: '8px',
                  userSelect: 'none',
                }}
                title="Trata madeira, pedras, minérios e recursos básicos como matérias-primas terminais, evitando poluir a árvore com etapas triviais"
              >
                <input
                  type="checkbox"
                  checked={pruneBasic}
                  onChange={(e) => setPruneBasic(e.target.checked)}
                  style={{ accentColor: '#14b8a6', cursor: 'pointer' }}
                />
                <span style={{ fontSize: '12px', fontWeight: 600, color: pruneBasic ? '#2dd4bf' : '#94a3b8' }}>
                  Omitir Cadeias Básicas
                </span>
              </label>

              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                  backgroundColor: avoidMystical ? '#7c2d1222' : '#1e293b',
                  border: `1px solid ${avoidMystical ? '#ea580c' : '#334155'}`,
                  padding: '6px 14px',
                  borderRadius: '8px',
                  userSelect: 'none',
                }}
                title="Evita atalhos de essências do Mystical Agriculture, priorizando máquinas e processos autênticos (ex: Energizing Orb, Altar, etc.)"
              >
                <input
                  type="checkbox"
                  checked={avoidMystical}
                  onChange={(e) => setAvoidMystical(e.target.checked)}
                  style={{ accentColor: '#ea580c', cursor: 'pointer' }}
                />
                <span style={{ fontSize: '12px', fontWeight: 600, color: avoidMystical ? '#fb923c' : '#94a3b8' }}>
                  Bloquear Mystical Agriculture
                </span>
              </label>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', color: '#94a3b8' }}>Quantidade:</span>
                <input
                  type="number"
                  min="1"
                  value={targetCount}
                  onChange={(e) => setTargetCount(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{ width: '80px', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '6px', color: '#fff', padding: '6px 10px', textAlign: 'center', fontWeight: 'bold' }}
                />
              </div>

              <button
                onClick={saveAsGoal}
                style={{ backgroundColor: '#0284c7', border: 'none', borderRadius: '6px', color: '#fff', padding: '8px 16px', fontSize: '13px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Target size={16} /> Salvar Objetivo
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #1e293b', paddingBottom: '12px', marginBottom: '20px' }}>
            {[
              { id: 'graph', label: 'Árvore Interativa', icon: Layers },
              { id: 'steps', label: `Etapas de Produção (${treeResult?.steps.length || 0})`, icon: ChevronRight },
              { id: 'materials', label: `Materiais Consolidados (${treeResult?.raw_materials.length || 0})`, icon: Cpu },
              { id: 'recipes', label: `Receitas do Item (${itemRecipes.length})`, icon: RefreshCw },
              { id: 'goals', label: `Progresso de Objetivos`, icon: Target },
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '8px 16px',
                    borderRadius: '8px',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: 600,
                    backgroundColor: activeTab === tab.id ? '#1e293b' : 'transparent',
                    color: activeTab === tab.id ? '#38bdf8' : '#94a3b8',
                  }}
                >
                  <Icon size={16} />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Warnings Banner if Cycles or Incomplete */}
          {treeResult?.has_circular_dependency && (
            <div style={{ padding: '12px 16px', backgroundColor: '#450a0a', border: '1px solid #dc2626', borderRadius: '8px', color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', fontSize: '13px' }}>
              <AlertTriangle size={18} />
              <span>Atenção: Dependência circular detectada nesta cadeia (ex: blocos ↔ lingotes ou essências). O motor preveniu recursão infinita e marcou as folhas circulares.</span>
            </div>
          )}

          {/* Tab 1: Interactive Graph View */}
          {activeTab === 'graph' && treeResult && (
            <div>
              <div style={{ marginBottom: '8px', fontSize: '12px', color: '#64748b' }}>
                Clique em qualquer nó para inspecionar ou alterar suas receitas alternativas. Arraste e dê zoom para navegar.
              </div>
              <GraphView rootNode={treeResult.root_node} onSelectNode={(key) => setSelectedItem(key)} />
            </div>
          )}

          {/* Tab 2: Sequential Steps */}
          {activeTab === 'steps' && treeResult && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {treeResult.steps.map((st, idx) => (
                <div key={st.step_id} style={{ backgroundColor: '#131e33', border: '1px solid #1e293b', borderRadius: '8px', padding: '14px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    {/* Output item texture icon */}
                    <div style={{ width: '40px', height: '40px', backgroundColor: '#0b1120', border: '1px solid #334155', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <img
                        src={`${API_BASE}/items/${encodeURIComponent(st.output.resource_id)}/icon`}
                        alt={st.output.resource_id}
                        style={{ width: '32px', height: '32px', imageRendering: 'pixelated', objectFit: 'contain' }}
                        onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                      />
                    </div>
                    <div>
                      <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 'bold' }}>PASSO {idx + 1} • {st.recipe_type}</span>
                      <div style={{ fontSize: '15px', fontWeight: 'bold', marginTop: '2px', color: '#f8fafc' }}>
                        Produzir {st.output.count}x {st.output.display_name || formatItemName(st.output.resource_id)}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                        {st.output.resource_id}
                      </div>
                      <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                          <img
                            src={`${API_BASE}/items/${encodeURIComponent(st.station_id || 'minecraft:crafting_table')}/icon`}
                            alt={st.machine_name || 'Máquina'}
                            style={{ width: '18px', height: '18px', imageRendering: 'pixelated', objectFit: 'contain', backgroundColor: '#0b1120', borderRadius: '4px', border: '1px solid #334155' }}
                            onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                          />
                          <span>Máquina: <strong style={{ color: '#e2e8f0' }}>{st.machine_name || 'Bancada de Trabalho'}</strong></span>
                        </span>
                        <span>• Lotes a executar: <strong style={{ color: '#fde047' }}>{st.runs_needed}x</strong></span>
                      </div>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>Insumos Necessários:</div>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                      {st.inputs.map((inp, iIdx) => (
                        <div key={iIdx} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', backgroundColor: '#0b1120', border: '1px solid #1e293b', borderRadius: '4px', padding: '2px 6px', fontSize: '11px', color: '#cbd5e1' }} title={inp.resource_id}>
                          <img
                            src={`${API_BASE}/items/${encodeURIComponent(inp.resource_id)}/icon`}
                            alt={inp.resource_id}
                            style={{ width: '16px', height: '16px', imageRendering: 'pixelated', objectFit: 'contain' }}
                            onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                          />
                          <span>{inp.count}x {inp.display_name || formatItemName(inp.resource_id)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Tab 3: Consolidated Materials */}
          {activeTab === 'materials' && treeResult && (
            <div>
              <h3 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '12px', color: '#38bdf8' }}>Matérias-Primas de Base (Consolidadas)</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px', marginBottom: '24px' }}>
                {treeResult.raw_materials.map((m) => (
                  <div key={m.item_key} style={{ backgroundColor: '#131e33', border: '1px solid #1e293b', borderRadius: '8px', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <img
                      src={`${API_BASE}/items/${encodeURIComponent(m.resource_id)}/icon`}
                      alt={m.resource_id}
                      style={{ width: '32px', height: '32px', imageRendering: 'pixelated', objectFit: 'contain' }}
                      onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: '11px', color: '#10b981', fontWeight: 600 }}>
                        {m.mod_name || formatModName(m.resource_id.split(':')[0])}
                      </div>
                      <div style={{ fontSize: '15px', fontWeight: 'bold', color: '#f8fafc', marginTop: '2px' }}>
                        {m.display_name || formatItemName(m.resource_id)}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                        {m.resource_id}
                      </div>
                      <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#38bdf8', marginTop: '4px' }}>
                        {m.total_needed} un.
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {treeResult.catalysts.length > 0 && (
                <>
                  <h3 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '12px', color: '#eab308' }}>Catalisadores e Moldes (Não Consumidos)</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
                    {treeResult.catalysts.map((c) => (
                      <div key={c.item_key} style={{ backgroundColor: '#131e33', border: '1px solid #713f12', borderRadius: '8px', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <img
                          src={`${API_BASE}/items/${encodeURIComponent(c.resource_id)}/icon`}
                          alt={c.resource_id}
                          style={{ width: '32px', height: '32px', imageRendering: 'pixelated', objectFit: 'contain' }}
                          onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                        />
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: '11px', color: '#eab308', fontWeight: 600 }}>
                            {c.mod_name || formatModName(c.resource_id.split(':')[0])}
                          </div>
                          <div style={{ fontSize: '15px', fontWeight: 'bold', color: '#f8fafc', marginTop: '2px' }}>
                            {c.display_name || formatItemName(c.resource_id)}
                          </div>
                          <div style={{ fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                            {c.resource_id}
                          </div>
                          <div style={{ fontSize: '14px', color: '#fef08a', marginTop: '4px' }}>
                            Exige {c.total_needed}x (reutilizável)
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Tab 4: Available Recipes for Item */}
          {activeTab === 'recipes' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '4px' }}>
                Selecione qual receita você prefere utilizar para produzir <b>{treeResult?.target_display_name || formatItemName(selectedItem)}</b>:
              </div>
              {itemRecipes.map((r) => {
                const isSelected = selectedRecipesMap[selectedItem] === r.recipe_id || (!selectedRecipesMap[selectedItem] && itemRecipes[0]?.recipe_id === r.recipe_id);
                return (
                  <div
                    key={r.recipe_id}
                    onClick={() => selectAlternativeRecipe(selectedItem, r.recipe_id)}
                    style={{
                      backgroundColor: isSelected ? '#1e293b' : '#131e33',
                      border: `2px solid ${isSelected ? '#38bdf8' : '#1e293b'}`,
                      borderRadius: '8px',
                      padding: '16px',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '14px', fontWeight: 'bold', color: '#f8fafc' }}>
                        {r.recipe_id}
                      </span>
                      {isSelected && (
                        <span style={{ backgroundColor: '#0369a1', color: '#fff', fontSize: '11px', padding: '2px 8px', borderRadius: '4px' }}>
                          SELECIONADA
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>Tipo: {r.recipe_type}</span>
                      <span>•</span>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <img
                          src={`${API_BASE}/items/${encodeURIComponent(r.machine_info?.station_id || 'minecraft:crafting_table')}/icon`}
                          alt="Estação"
                          style={{ width: '18px', height: '18px', imageRendering: 'pixelated', objectFit: 'contain', backgroundColor: '#0b1120', borderRadius: '4px', border: '1px solid #334155' }}
                          onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                        />
                        <span>Estação: <strong style={{ color: '#e2e8f0' }}>{r.machine_info?.station_name || 'Bancada de Trabalho'}</strong></span>
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '10px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <span style={{ color: '#64748b' }}>Ingredientes:</span>
                      {r.inputs.map((i, inIdx) => {
                        const alt = i.alternatives[0];
                        if (!alt) return null;
                        return (
                          <div key={inIdx} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', backgroundColor: '#0b1120', border: '1px solid #334155', borderRadius: '4px', padding: '2px 6px', fontSize: '11px' }} title={alt.resource_id}>
                            <img
                              src={`${API_BASE}/items/${encodeURIComponent(alt.resource_id)}/icon`}
                              alt={alt.resource_id}
                              style={{ width: '16px', height: '16px', imageRendering: 'pixelated', objectFit: 'contain' }}
                              onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                            />
                            <span>{i.count}x {formatItemName(alt.resource_id)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Tab 5: Goals & Tracking */}
          {activeTab === 'goals' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {goals.map((g) => (
                <div key={g.goal_id} style={{ backgroundColor: '#131e33', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 'bold' }}>{g.title}</h4>
                      <span style={{ fontSize: '12px', color: '#64748b' }}>Criado em: {new Date(g.created_at).toLocaleString()}</span>
                    </div>
                    <button
                      onClick={() => {
                        setSelectedItem(g.target_item_key);
                        setTargetCount(g.target_count);
                        setActiveTab('steps');
                      }}
                      style={{ backgroundColor: '#1e293b', border: '1px solid #334155', color: '#38bdf8', borderRadius: '6px', padding: '6px 12px', fontSize: '12px', cursor: 'pointer' }}
                    >
                      Abrir Plano Detalhado
                    </button>
                  </div>

                  <div style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '8px' }}>
                    Marque as etapas já concluídas no seu mundo:
                  </div>
                  {treeResult?.steps.slice(0, 10).map((st) => {
                    const isDone = g.completed_steps.includes(st.step_id);
                    return (
                      <div
                        key={st.step_id}
                        onClick={() => toggleGoalStep(g.goal_id, st.step_id)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          padding: '8px 12px',
                          borderRadius: '6px',
                          backgroundColor: isDone ? '#064e3b' : '#1e293b',
                          marginBottom: '6px',
                          cursor: 'pointer',
                          textDecoration: isDone ? 'line-through' : 'none',
                          color: isDone ? '#6ee7b7' : '#e2e8f0',
                          fontSize: '13px',
                        }}
                      >
                        <CheckCircle size={16} color={isDone ? '#10b981' : '#64748b'} />
                        <span>Produzir {st.output.count}x {st.output.resource_id} ({st.machine_name || 'Bancada'})</span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default App;

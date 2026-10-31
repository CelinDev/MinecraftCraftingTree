export interface RecipeStack {
  resource_id: string;
  item_key: string;
  display_name?: string;
  count: number;
  resource_type: string;
  nbt?: string;
  chance: number;
  is_primary: boolean;
}

export interface IngredientSlot {
  alternatives: RecipeStack[];
  count: number;
  consumable: boolean;
  chance: number;
  slot_key?: string;
}

export interface MachineInfo {
  station_id: string;
  station_name: string;
  energy_fe?: number;
  ticks?: number;
  tier?: string;
}

export interface Recipe {
  recipe_id: string;
  recipe_type: string;
  source_mod: string;
  data_source: string;
  output_item_id: string;
  output_count: number;
  outputs: RecipeStack[];
  inputs: IngredientSlot[];
  machine_info?: MachineInfo;
  validation_status: string;
  warnings?: string[];
  extra_data?: any;
  raw_data?: any;
}

export interface DependencyNode {
  node_id: string;
  item_key: string;
  resource_id: string;
  display_name?: string;
  mod_name?: string;
  resource_type: string;
  count: number;
  status: string;
  selected_recipe_id?: string;
  station_id?: string;
  station_name?: string;
  available_recipes_count: number;
  runs_needed: number;
  produced_count: number;
  excess_count: number;
  is_catalyst: boolean;
  warning?: string;
  depth: number;
  children: DependencyNode[];
}

export interface CraftingStep {
  step_id: string;
  recipe_id: string;
  recipe_type: string;
  source_mod: string;
  output: RecipeStack;
  runs_needed: number;
  inputs: RecipeStack[];
  machine_name?: string;
  station_id?: string;
  depth: number;
}

export interface ConsolidatedMaterial {
  item_key: string;
  resource_id: string;
  display_name?: string;
  mod_name?: string;
  resource_type: string;
  total_needed: number;
  is_catalyst: boolean;
  nbt?: string;
}

export interface CraftingTreeResult {
  target_item_key: string;
  target_display_name?: string;
  target_mod_name?: string;
  target_count: number;
  root_node: DependencyNode;
  steps: CraftingStep[];
  raw_materials: ConsolidatedMaterial[];
  catalysts: ConsolidatedMaterial[];
  byproducts: RecipeStack[];
  has_circular_dependency: boolean;
  has_incomplete_recipes: boolean;
}

export interface SearchItem {
  item_id: string;
  display_name: string;
  source_mod: string;
  mod_name: string;
  recipes_count: number;
}

export interface CraftingGoal {
  goal_id: string;
  title: string;
  target_item_key: string;
  target_count: number;
  status: string;
  created_at: string;
  updated_at: string;
  completed_steps: string[];
}


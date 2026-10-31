/**
 * Formatting utilities for Minecraft items, blocks, and mods.
 */

export function formatItemName(itemKey?: string, displayName?: string): string {
  if (displayName && displayName.trim()) {
    return displayName;
  }
  if (!itemKey) return '';
  const clean = itemKey.replace(/^#/, '');
  const id = clean.includes(':') ? clean.split(':')[1] : clean;
  if (itemKey.startsWith('#') || itemKey.startsWith('forge:')) {
    const parts = id.split('/');
    const main = parts[parts.length - 1];
    return main.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) + ' (Tag)';
  }
  return id
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatModName(modId?: string): string {
  if (!modId) return '';
  const MOD_NAMES: Record<string, string> = {
    minecraft: 'Minecraft',
    powah: 'Powah!',
    mekanism: 'Mekanism',
    thermal: 'Thermal Series',
    enderio: 'Ender IO',
    botania: 'Botania',
    bloodmagic: 'Blood Magic',
    nuclearcraft: 'NuclearCraft',
    actuallyadditions: 'Actually Additions',
    extendedcrafting: 'Extended Crafting',
    avaritia: 'Avaritia',
    cyclic: 'Cyclic',
    mysticalagriculture: 'Mystical Agriculture',
    mysticalagradditions: 'Mystical Agradditions',
    ae2: 'Applied Energistics 2',
    exdeorum: 'Ex Deorum',
    hostilenetworks: 'Hostile Neural Networks',
    integrateddynamics: 'Integrated Dynamics',
    tconstruct: "Tinkers' Construct",
    draconicevolution: 'Draconic Evolution',
    kubejs: 'KubeJS',
    sophisticatedstorage: 'Sophisticated Storage',
    sophisticatedbackpacks: 'Sophisticated Backpacks',
    botanypots: 'Botany Pots',
    pneumaticcraft: 'PneumaticCraft',
    compressium: 'Compressium',
    allthemodium: 'Allthemodium',
    industrialforegoing: 'Industrial Foregoing',
  };
  return MOD_NAMES[modId.toLowerCase()] || modId.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}


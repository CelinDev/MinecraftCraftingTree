# Relatório de Auditoria Técnica — Project Infinity 0.1

**Data da Auditoria:** 29/10/2026  
**Fase do Projeto:** Fase 1 — Auditoria do Modpack  
**Diretório Inspecionado:** `C:\Users\olx\curseforge\minecraft\Instances\Project Infinity 0.1`  
**Diretório Base do Launcher:** `C:\Users\olx\curseforge\minecraft\Install`

---

## 1. Identificação da Instalação

A instalação local do modpack **Project Infinity 0.1** foi localizada no diretório padrão do CurseForge e inspecionada integralmente em modo somente leitura (nenhum arquivo do modpack foi modificado).

| Propriedade | Valor Identificado | Fonte da Evidência |
| :--- | :--- | :--- |
| **Nome do Modpack** | Project Infinity 0.1 | `manifest.json` / `minecraftinstance.json` |
| **Versão do Modpack** | `0.0.52.1` | `manifest.json` / `kubejs/todo.txt` |
| **Autor do Modpack** | `BOLT_M4G1C` | `manifest.json` |
| **Versão do Minecraft** | `1.20.1` (Java Edition) | `manifest.json` e `Install/versions/1.20.1/1.20.1.jar` |
| **Mod Loader** | **Minecraft Forge** | `manifest.json` (`id: "forge-47.4.28"`, `primary: true`) |
| **Versão do Forge** | `47.4.28` | `manifest.json` / `minecraftinstance.json` |
| **RAM Recomendada** | `10240 MB` (10 GB) | `manifest.json` |
| **Mods no Manifesto** | `371` entradas (367 mods `.jar` + 4 resourcepacks `.zip`) | `manifest.json` / `modlist.html` |
| **Mods Instalados (`mods/`)** | **`368` arquivos `.jar`** (367 do manifesto + `cc-tweaked-1.20.1-forge-1.120.0.jar` via override) | Diretório `mods/` |
| **Estado de Execução** | **Iniciado e validado em execução real** — `logs/latest.log`, `logs/kubejs/startup.log`, `client.log` e `server.log` inspecionados com 0 erros de script. | `logs/` |

---

## 1.1. Métricas Reais de Execução Capturadas nos Logs do Jogo

Após a primeira execução da instância, inspecionamos `logs/latest.log` e `logs/kubejs/*.log`, obtendo a confirmação exata do pipeline interno do Minecraft + Forge + KubeJS + Almost Unified + JEI:

- **Scripts KubeJS Carregados:**
  - `26/26` `startup_scripts` carregados em `3.854 s` com **0 erros e 0 avisos**.
  - `6/6` `client_scripts` carregados em `0.095 s` com **0 erros e 0 avisos**.
  - `301/301` `server_scripts` carregados em `0.399 s` com **0 erros e 0 avisos**.
- **Mutação de Tags (`tags.js` + Datapacks):**
  - `[minecraft:item]`: **3.725 tags** encontradas, **380 objetos adicionados**, **393 objetos removidos**.
  - `[minecraft:block]`: **1.727 tags** encontradas, **268 objetos adicionados**, **1 objeto removido**.
  - `[minecraft:fluid]`: **1.337 tags** encontradas, **18 objetos adicionados**, **0 objetos removidos**.
- **Processamento do `RecipeManager` + KubeJS (`latest.log` às `01:50:00` – `01:50:14`):**
  - **Receitas base elegíveis após condições Forge/Bookshelf:** `32.072` receitas encontradas em `1.100 s`.
  - **Singularidades Extended Crafting carregadas:** `81` tipos em `1.260 ms`.
  - **Jetpacks IronJetpacks carregados:** `14` tipos em `180 ms`.
  - **Processos Masterful Machinery registrados:** `132` receitas em `1.509 ms` (`KubeJS mode`).
  - **Culturas Mystical Agriculture lidas pelo JEI:** `156` crops.
  - **Balanço final consolidado pelo KubeJS:**
    > `Added 29134 recipes, removed 3996 recipes, modified 148 recipes, with 3 failed recipes in 3.316 s`
    *(Seguido por +45 receitas injetadas pelo HammerLib e +22 adicionais, totalizando **~29.201 receitas ativas** no jogo).*

---

## 2. Estrutura dos Diretórios

A árvore de diretórios da instância contém **3.774 arquivos** distribuídos da seguinte forma:

```text
Project Infinity 0.1/
├── config/                  (1.383 arquivos em 54 subpastas — configurações de mods, Almost Unified, Singularidades, Masterful Machinery, ProjectE, etc.)
├── defaultconfigs/          (21 arquivos .toml e .snbt — configurações padrão de servidor copiadas para mundos novos)
├── kubejs/                  (1.997 arquivos — centro de personalização de itens, blocos, máquinas, tags e receitas do modpack)
│   ├── assets/              (889 arquivos — texturas, modelos, guias Patchouli/AE2 e traduções)
│   ├── client_scripts/      (6 arquivos .js — ocultação de itens no JEI e tooltips)
│   ├── config/              (3 arquivos — configuração interna do KubeJS)
│   ├── data/                (767 arquivos em 41 namespaces — datapack global injetado pelo KubeJS)
│   ├── server_scripts/      (301 arquivos .js — adição, remoção, substituição de receitas, tags e eventos de mundo)
│   └── startup_scripts/     (26 arquivos .js — registro de novos itens, blocos, fluidos e controladores Masterful Machinery)
├── mods/                    (368 arquivos .jar — todos os mods ativos na instância)
├── profileImage/            (1 arquivo — ícone do perfil no CurseForge)
├── resourcepacks/           (4 arquivos .zip — pacotes de textura do modpack)
├── saves/                   (0 arquivos — nenhum mundo criado ainda)
├── manifest.json            (Manifesto oficial CurseForge)
├── minecraftinstance.json   (Metadados detalhados da instância gerados pelo CurseForge)
├── modlist.html             (Lista HTML dos 371 addons listados no manifesto)
└── servers.dat              (Lista de servidores pré-configurada)
```

---

## 3. Ferramentas de Personalização e Unificação Identificadas

Confirmamos a presença (ou ausência) das principais ferramentas de modificação de receitas por meio da inspeção dos arquivos `.jar` em `mods/` e pastas em `config/`:

1. **KubeJS (`kubejs-forge-2001.6.5-build.26.jar`) — PRESENTE E CENTRAL:**
   - Principal motor de personalização do modpack.
   - Possui addons dedicados instalados:
     - `kubejs-thermal-2001.1.10-build.5.jar` (integração com máquinas da série Thermal).
     - `kubejs_enderio-forge-1.20.1-0.6.1.jar` (integração com máquinas do EnderIO).
     - `lootjs-forge-1.20.1-2.13.1.jar` (modificação de tabelas de loot via scripts em `kubejs/server_scripts/lootjs/`).
     - `morejs-forge-1.20.1-0.10.1.jar` (desativação de trocas de aldeões e mecânicas de encantamento).
2. **CraftTweaker — AUSENTE:**
   - Não há nenhum arquivo `.jar` do CraftTweaker em `mods/` nem diretório `scripts/` com arquivos `.zs`.
3. **Almost Unified (`almostunified-forge-1.20.1-0.11.0.jar`) — PRESENTE:**
   - Configurado em `config/almostunified/unify.json`.
   - Unifica automaticamente tags de `47` materiais (minérios, lingotes, pós, engrenagens, placas, pepitas, blocos) em tempo de carregamento das receitas, seguindo a ordem de prioridade: `["minecraft", "kubejs", "thermal", "mekanism", "common_ore_library"]` (com exceção explícita de `forge:ingots/signalum` para `thermal`).
4. **Masterful Machinery (`MasterfulMachinery-3-1.20.1-0.1.35.10.jar`) — PRESENTE:**
   - Define **15 estruturas multibloco customizadas** do modpack (ex.: *Infinity Crucible*, *Infinity Cell Factory*, *EssenceForge*, *Event Horizon Antimatter Synthesizer*, *Auto Sieve*, *Auto Crusher*, *Mechanical Empowerer*, *Loot Fabrication Plant*, *Prediction Chamber*, etc.).
   - Controladores e portas são registrados em `kubejs/startup_scripts/masterfull_machinery/` e `config/mm/pack/`, enquanto as estruturas e os processos (receitas) são registrados via `MMEvents.createStructures` e `MMEvents.createProcesses` em `kubejs/server_scripts/mods_recipes/masterfull_machinery/`.
5. **Extended Crafting (`ExtendedCrafting-1.20.1-6.1.9.jar`) e Re-Avaritia (`Re-Avaritia-forge-1.20.1-1.4.2-release.jar`) — PRESENTES:**
   - `config/extendedcrafting/singularities/` define **81 singularidades** ativas (geram receitas dinâmicas no *Quantum Compressor* e compõem a *Ultimate Singularity*).
   - `config/avaritia/singularities/` possui 20 arquivos `.json`, porém **todos os 20 estão desativados** (`"enabled": false, "recipeDisabled": true`), pois o modpack unificou o sistema de singularidades no Extended Crafting (confirmado também por `replace_items.js`).
6. **Mystical Customization (`MysticalCustomization-1.20.1-5.0.3.jar`) — PRESENTE:**
   - `config/mysticalcustomization/crops/` define **14 sementes/plantas customizadas** (ex.: `allthemodium`, `unobtainium`, `vibranium`, `ultimate`, `ultimate_infinity`, `dark_metal_ingot`, `ignitium`, `sky_steel`, etc.) e 2 novos tiers (`7` e `8`). As receitas de infusão padrão dessas sementes são desativadas (`"infusion": false`) para exigir crafting customizado via KubeJS/Extended Crafting.
7. **ProjectE (`ProjectE-1.20.1-PE1.0.1.jar`), Project Expansion e Project Extended — PRESENTES:**
   - `config/ProjectE/custom_emc.json` e `pregenerated_emc.json` definem valores de EMC. Vale notar que diversos itens do modpack têm EMC removido ou ajustado para não quebrar a progressão.
8. **JEI (`jei-1.20.1-forge-15.56.0.205.jar`) — PRESENTE:**
   - Visualizador de receitas oficial utilizado pelo modpack (EMI não está instalado).

---

## 4. Fontes de Receitas e Quantidades Detectadas

Realizamos uma varredura automatizada em todos os arquivos `.jar`, datapacks, scripts `.js` e configurações da instância. Abaixo está o inventário exato por fonte:

### 4.1. Resumo Quantitativo por Fonte

| Fonte de Dados | Localização | Arquivos / Registros Detectados | Observações Técnicas |
| :--- | :--- | :--- | :--- |
| **1. Receitas Vanilla** | `Install/versions/1.20.1/1.20.1.jar` (`data/minecraft/recipes/`) | **1.174** arquivos `.json` | Receitas base do Minecraft 1.20.1 (Shaped, Shapeless, Smelting, Blasting, Smoking, Campfire, Stonecutting, Smithing). |
| **2. Receitas JSON dos Mods** | `mods/*.jar` (202 de 368 JARs possuem `data/*/recipes/*.json`) | **36.953** arquivos `.json` | Distribuídos em **450 tipos (`type`) distintos** (top mods: NuclearCraft com 4.274, Mekanism com 4.223, BetterBlockz com 2.852, ExDeorum com 2.104, BotanyPots com 1.797, Botania com 1.302, MysticalAgriculture com 1.167, EnderIO com 1.163). |
| **3. Datapack KubeJS (`kubejs/data`)** | `kubejs/data/*/recipes/*.json` | **417** arquivos `.json` | Sendo **300 receitas ativas** (ex.: 126 `thermal:crucible`, 31 `botanypots:crop`, 26 `draconicevolution:fusion_crafting`, 19 `functionalstorage:custom_compacting`, etc.) e **117 arquivos vazios (`{}`)** usados para sobrescrever/desativar receitas de mods pelo mesmo ResourceLocation ID. |
| **4. Modelos Hostile Neural Networks** | `kubejs/data/hostilenetworks/data_models/*.json` (e JARs) | **44** arquivos `.json` em `kubejs/data` | Definem qual matéria/item base e qual *prediction* geram drops no *Loot Fabricator* e *Simulation Chamber*. |
| **5. Scripts KubeJS (`server_scripts`)** | `kubejs/server_scripts/**/*.js` (301 arquivos `.js`) | **~750+ adições** + **~600+ remoções** + **121 substituições** | Inclui 408 chamadas de funções auxiliares (`create3x3`, `create3x3same`, `seedtiercrafting*`, etc. definidas em `functions.js`), ~200+ chamadas `event.custom({...})`, ~118 chamadas diretas (`shaped`, `shapeless`, `smelting`, `blasting`, `stonecutting`, `smithing`), **132 receitas Masterful Machinery** (`MMEvents.createProcesses`), **119 `replaceInput`**, **2 `replaceOutput`** e **~602+ remoções** em `remove_recipes.js`. |
| **6. Singularidades (Configs)** | `config/extendedcrafting/singularities/*.json` | **81** arquivos `.json` ativos | Cada arquivo gera dinamicamente uma receita de compressão (ex.: 5.000 lingotes -> 1 Singularidade) e compõe os ingredientes da `extendedcrafting:ultimate_singularity`. |
| **7. Interações de Mundo KubeJS** | `kubejs/server_scripts/scripts/world_interaction_scripts/*.js` | **14** arquivos `.js` | Eventos `BlockEvents.rightClicked` / `ItemEvents.rightClicked` (ex.: `pebble_from_dirt_grass.js`, `ae2_give_back_ingredients.js`, `extra_data_model_uncrafter.js`). |

---

## 5. Formatos de Receita Encontrados

A auditoria identificou **6 categorias estruturais de formatos de receitas** no Project Infinity 0.1:

### 5.1. Formatos Padrão Minecraft / Forge (JSON e KubeJS)
- `minecraft:crafting_shaped` / `crafting_shaped` / `cucumber:shaped_no_mirror` (8.544 nos JARs + centenas via KubeJS `event.shaped` e helpers `create3x3`, `create323`, `create2x2`, etc.)
- `minecraft:crafting_shapeless` (3.894 nos JARs + `event.shapeless` no KubeJS)
- `minecraft:smelting` (643), `minecraft:blasting` (300), `minecraft:smoking`, `minecraft:campfire_cooking`
- `minecraft:stonecutting` (4.082)
- `minecraft:smithing_transform` (245) e `minecraft:smithing_trim`

### 5.2. Envelopes Condicionais (Wrappers)
Muito frequentes nos JARs dos mods e em `kubejs/data`:
- `forge:conditional` (**1.633** nos JARs + 1 em `kubejs/data`): encapsula um array `recipes` protegido por condições (`forge:mod_loaded`, `forge:not`, `forge:tag_empty`, `bookshelf:item_exists`, `thermal:flag`, etc.).
- `bookshelf:item_exists` (**1.449** nos JARs + 19 em `kubejs/data`): carrega a receita somente se o item existir no registro.

### 5.3. Sistemas de Crafting Endgame (Grades Maiores e Fusão)
Essenciais para a árvore de dependências principal do Project Infinity 0.1 (`kubejs:infinity_1` até `kubejs:infinity_12`, itens criativos, armaduras e máquinas finais):
- **Extended Crafting:**
  - `extendedcrafting:shaped_table` (grades 3x3, 5x5, 7x7 e 9x9 — **121 receitas customizadas no KubeJS**, especialmente em `mods_recipes/extendedcrafting/endgame_items/` e `seed_crafting/`).
  - `extendedcrafting:shapeless_table` (16 no KubeJS).
  - `extendedcrafting:combination` (Crafting Core + Pedestais — 8 no KubeJS).
  - `extendedcrafting:compressor` (Quantum Compressor — gerado dinamicamente pelas 81 singularidades em `config/extendedcrafting/singularities/`).
  - `extendedcrafting:shaped_ender_crafter` e `extendedcrafting:shaped_flux_crafter`.
- **Re-Avaritia:**
  - `avaritia:shaped_table` / `avaritia:extreme_craft` (Extreme Crafting Table 9x9).
- **Draconic Evolution:**
  - `draconicevolution:fusion_crafting` (26 arquivos em `kubejs/data/draconicevolution/recipes/machines/` + 2 via KubeJS; requer *Fusion Crafting Core*, *Injetores* de tier específico — `DRACONIUM`, `WYVERN`, `DRACONIC`, `CHAOTIC` — e custo de energia RF/FE).

### 5.4. Máquinas Tecnológicas e Processamento Multi-Input / Multi-Output / Fluidos / Gases
- **Mekanism / Evolved Mekanism / Mekanism Extras:**
  - `mekanism:sawing` (1.804), `mekanism:painting` (976), `mekanism:crushing` (341), `mekanism:enriching` (303), `mekanism:pigment_extracting` (206), `mekanism:metallurgic_infusing`, `mekanism:reaction` (Pressurized Reaction Chamber — consome Item + Fluido + Gás e produz Item + Gás), `mekanism:dissolution`, `mekanism:crystallizing`, `mekanism:injecting`, `mekanism:purifying`, `mekanism:combining`, `mekanism:nucleosynthesizing`, `mekanism:oxidizing`, `mekanism:rotary` (conversão gás <-> fluido), `evolvedmekanism:alloying` (Alloyer — combina 3 itens simultaneamente).
  - *Nota importante:* `mekanism:mek_data` (154 receitas) é um wrapper de crafting shaped que preserva dados internos (energia, fluidos, gases e upgrades) ao fazer upgrade de tier de máquinas/cubos/tanques do Mekanism.
- **Thermal Series / Thermal Extra / Thermal Processing:**
  - `thermal:press` (568), `thermal:insolator` (232 nos JARs, porém **removido globalmente** em `remove_recipes.js`!), `thermal:smelter` (Induction Smelter — 187), `thermal:pulverizer` (185), `thermal:chiller` (157), `thermal:crucible` (Magma Crucible — 150 nos JARs + **126 em `kubejs/data/thermal_processing/`**), `thermal:bottler` (Fluid Encapsulator), `thermal:crystallizer`, `thermal:refinery`, `thermal:centrifuge`, `thermal:pyrolyzer`, `thermal_extra:advanced_refinery`, `thermal_extra:fluid_mixer`, `thermal_extra:component_assembly`, `thermal_extra:endothermic_dehydrator`.
- **NuclearCraft:**
  - `nuclearcraft:melter` (604), `nuclearcraft:target_chamber` (441), `nuclearcraft:ingot_former` (288), `nuclearcraft:fluid_infuser` (190), `nuclearcraft:chemical_reactor` (169), `nuclearcraft:alloy_smelter`, `nuclearcraft:irradiator`, `nuclearcraft:manufactory`, `nuclearcraft:pressurizer`, `nuclearcraft:rock_crusher`, `nuclearcraft:supercooler`, `nuclearcraft:assembler`, `nuclearcraft:centrifuge`, `nuclearcraft:crystallizer`, `nuclearcraft:electrolyzer`, `nuclearcraft: fluid_enricher`.
- **EnderIO:**
  - `enderio:alloy_smelting` (Alloy Smelter), `enderio:sag_milling` (SAG Mill — saídas múltiplas com probabilidade), `enderio:slicing` (Slice'N'Splice), `enderio:soul_binding` (Soul Binder), `enderio:painting`, `enderio:tank`.
- **Industrial Foregoing & PneumaticCraft:**
  - `industrialforegoing:dissolution_chamber` (até 8 itens + 1 fluido -> 1 item + 1 fluido; **19 receitas adicionadas no KubeJS**), `industrialforegoing:laser_drill_ore`, `industrialforegoing:laser_drill_fluid`, `industrialforegoing:fluid_extractor`, `industrialforegoing:stonework_generate`.
  - `pneumaticcraft:pressure_chamber` (suporta `pneumaticcraft:stacked_item` com quantidades > 1 por slot), `pneumaticcraft:thermo_plant`, `pneumaticcraft:assembly_laser`, `pneumaticcraft:assembly_drill`, `pneumaticcraft:fluid_mixer`, `pneumaticcraft:refinery`, `pneumaticcraft:amadron`.
- **Applied Energistics 2, AdvancedAE & CrazyAE2Addons:**
  - `ae2:inscriber` (Inscriber — top, middle, bottom, mode `inscribe` ou `press`), `ae2:charger`, `ae2:transform` (transformação em fluido no mundo).
  - `advanced_ae:reaction` (Reaction Chamber — múltiplos itens + fluido + energia -> item/fluido; 9 receitas no KubeJS + 1 em `kubejs/data`).
  - `crazyae2addons:cradle` (Entropy Cradle — 6 no KubeJS), `crazyae2addons:fabrication` (1 no KubeJS), `crazyae2addons:research` (1 no KubeJS + 1 em `kubejs/data`).
- **Powah, ExDeorum & BotanyPots:**
  - `powah:energizing` (Energizing Orb — itens + FE -> item; 14 em `kubejs/data` + 9 em `server_scripts`).
  - `exdeorum:sieve` (539 nos JARs + 59 no KubeJS — item peneirado + malha (`mesh`) -> drops probabilísticos), `exdeorum:hammer` (14 em `kubejs/data`), `exdeorum:crook`, `exdeorum:barrel_mixing`, `exdeorum:barrel_fluid_mixing`, `exdeorum:crucible`. *(Nota: `exdeorum:compressed_sieve` e `exdeorum:compressed_hammer` são removidos globalmente em `remove_recipes.js` pois o modpack usa multiblocos Masterful Machinery para processamento em massa).*
  - `botanypots:crop` (1.797 nos JARs + 31 em `kubejs/data` — define qual semente cresce em quais categorias de solo e quais itens produz).

### 5.5. Sistemas Mágicos e Rituais
- **Botania, MythicBotany & Botanical Extra Machinery:**
  - `botania:mana_infusion` (Mana Pool + catalisador opcional como Alchemy/Conjuration), `botania:runic_altar`, `botania:petal_apothecary`, `botania:elven_trade`, `botania:terra_plate` (Terrestrial Agglomeration Plate), `botania:Pure_daisy`, `botania:brew`, `mythicbotany:rune_ritual`, `mythicbotany:infuser`.
- **Blood Magic & Sanguine Networks:**
  - `bloodmagic:altar` (Blood Altar — tier do altar, consumo de LP), `bloodmagic:soulforge` (Hellfire Forge — tartaric gems), `bloodmagic:alchemytable` (Alchemy Table), `bloodmagic:array`, `bloodmagic:meteor`.
- **Mystical Agriculture:**
  - `mysticalagriculture:infusion` (Infusion Altar + 8 Pedestais), `mysticalagriculture:awakening` (Awakening Altar + 4 Essences vases), `mysticalagriculture:reprocessor` (Seed Reprocessor), `mysticalagriculture:enchanter`, `mysticalagriculture:soul_extraction`.

### 5.6. Masterful Machinery (`MMEvents.createProcesses`) — Formato Exclusivo via Script
- **132 receitas** definidas exclusivamente em JavaScript dentro de `kubejs/server_scripts/mods_recipes/masterfull_machinery/`.
- Não geram arquivos `.json` estáticos no disco antes da execução; são registradas via builder fluente do Masterful Machinery 3:
  - `.create('mm:<recipe_id>')`
  - `.structureId('mm:<structure_id>')` (associa a receita a uma das 15 máquinas multibloco)
  - `.ticks(<int>)`
  - `.input({ type: 'mm:input/consume', chance: <0.0..1.0>, ingredient: { type: 'mm:item' | 'mm:fluid' | 'mm:energy' | 'mm:mekanism/gas', ... } })`
  - `.output({ type: 'mm:output/simple', chance: <0.0..1.0>, ingredient: { type: 'mm:item' | 'mm:fluid' | 'mm:energy' | 'mm:mekanism/gas', ... } })`
- **Detalhe crucial:** Ingredientes com `chance: 0.0` atuam como **catalisadores não consumidos** (ex.: `kubejs:ultimate_heart`, `justdirethings:time_crystal`, malhas em peneiras automáticas). Além disso, algumas receitas exigem itens com **NBT específico** (`nbt_snbt` e `nbt_match: 'weak'`), como tanques do Mekanism cheios de um fluido específico ou `kubejs:fluid_tank_token`.

---

## 6. Diferença entre Receitas Originais dos JARs e Receitas Ativas no Jogo

**Por que ler apenas os arquivos `.jar` produziria uma árvore de crafting incorreta no Project Infinity 0.1?**

A auditoria comprovou que o Project Infinity 0.1 altera profundamente o grafo de receitas dos mods originais por meio de **quatro camadas de modificação**:

1. **Sobrescrita e Desativação por Datapack (`kubejs/data/`):**
   - **117 receitas** de mods (incluindo Avaritia, Blood Magic, Botanical Extra Machinery, Draconic Evolution, EnderIO, ExDeorum, Mekanism, Mystical Agriculture, Powah, Sanguine Networks, Thermal) são anuladas por arquivos `.json` vazios (`{}`) com o mesmo caminho/ID em `kubejs/data/`.
   - Outras **300 receitas** substituem ou adicionam processos customizados (ex.: 126 receitas de `thermal:crucible` em `kubejs/data/thermal_processing/`).
2. **Remoções em Massa via KubeJS (`remove_recipes.js`):**
   - **170 itens de saída (`removeRecipebyOutput`)** têm todas as suas receitas originais removidas (ex.: `projecte:philosophers_stone`, `projecte:transmutation_tablet`, `extendedcrafting:compressor`, `extendedcrafting:ultimate_table`, `enderio:alloy_smelter`, sementes do Mystical Agriculture, etc.).
   - **414 IDs de receitas específicos (`removeRecipebyRecipeID`)** são removidos individualmente.
   - **18 tipos inteiros de receitas (`removeRecipebyType`)** são completamente eliminados do jogo (ex.: `thermal:insolator`, `exdeorum:compressed_sieve`, `exdeorum:compressed_hammer`, `cyclic:crusher`, `cyclic:packager`, `bloodmagic:arcfurnace`, `packagedauto:*`).
   - **8 mods inteiros** têm todas as suas receitas removidas (`refinedstorage`, `extrastorage`, `rsrequestify`, `rsinfinitybooster`, `refinedstorageaddons`, `universalgrid`, `rftoolsdim`, `libraryferret`) em preparação para a remoção desses mods na versão 0.0.53.0.
   - **Filtros por Regex e Condições Composta:** Remoção de todas as receitas `mysticalagriculture:infusion` cujo output contenha `/seeds/` (pois todas as sementes foram movidas para receitas customizadas em tiers no KubeJS/Extended Crafting), remoção de `avaritia:shaped_table` com `/dragon_egg/`, etc.
3. **Substituição Global de Ingredientes (`replace_items.js` e scripts de mods):**
   - **119 chamadas `event.replaceInput`** e **2 chamadas `event.replaceOutput`** alteram ingredientes em receitas existentes (ex.: toda receita que pedia `projecte:philosophers_stone` passa a exigir `kubejs:fake_philosophers_stone`; toda receita que pedia `avaritia:eternal_singularity` ou `avaritia:singularity` passa a exigir `extendedcrafting:ultimate_singularity`).
4. **Modificações Dinâmicas de Tags (`kubejs/server_scripts/tags.js` + Almost Unified):**
   - Receitas dependem fortemente de tags (`#forge:ingots/steel`, `#forge:gears/enderium`, etc.). O script `tags.js` adiciona e remove itens de tags dinamicamente, enquanto o **Almost Unified** reescreve entradas e saídas das receitas em memória para apontar para o item prioritário (`minecraft > kubejs > thermal > mekanism > common_ore_library`).

---

## 7. Principais Limitações Encontradas

1. **Ambiente de Desenvolvimento Local (Python ausente no Windows):**
   - Ao testar o ambiente de execução local, verificamos que **Python não está instalado** (apenas o atalho da Microsoft Store em `WindowsApps\python3.exe` está presente).
   - O **Java** não está no `PATH` global do Windows, mas **está disponível localmente** através do instalador do CurseForge em:
     - `C:\Users\olx\curseforge\minecraft\Install\java\java-runtime-gamma\bin\java.exe` (Java 17 — runtime oficial do Minecraft 1.20.1)
     - `C:\Users\olx\curseforge\minecraft\Install\java\Jre_21\bin\java.exe` (Java 21)
2. **Modpack ainda não foi iniciado pela primeira vez:**
   - Como a instância acabou de ser instalada e nunca rodou, ainda não existem logs de execução (`logs/kubejs/server.log`) nem dumps gerados em tempo de execução.
3. **Natureza imperativa dos scripts KubeJS (`server_scripts`):**
   - Embora ~95% dos scripts KubeJS sigam padrões muito bem estruturados (helpers em `functions.js`, JSONs dentro de `event.custom({...})` e builders fluentes em `MMEvents.createProcesses`), alguns scripts usam laços `forEach`, arrays e expressões regulares em JavaScript para adicionar, remover ou modificar receitas e tags.
4. **Receitas Registradas Dinamicamente em Código Java (Runtime-Only):**
   - Certas receitas não existem como arquivos `.json` completos nem em scripts KubeJS:
     - Receitas do *Quantum Compressor* para as **81 singularidades** (geradas pelo código Java do Extended Crafting a partir dos arquivos em `config/extendedcrafting/singularities/*.json`).
     - Receitas de *Infusion/Reprocessor* para as **14 culturas customizadas** do Mystical Customization (`config/mysticalcustomization/crops/*.json`).
     - Receitas especiais baseadas em código (`minecraft:crafting_special_*`, recarga de baterias, facadas de cabos, clonagem de configurações, etc.).
5. **Processos com Semântica Especial:**
   - **Catalisadores não consumidos (`chance: 0.0`):** Muito comuns no Masterful Machinery e Extended Crafting/Mystical Agriculture (ex.: *Master Infusion Crystal*, *Ultimate Heart*). Se tratados como ingredientes normais consumidos, distorceriam o cálculo total de matérias-primas.
   - **Diferenciação por NBT:** Itens como `hostilenetworks:prediction`, `hostilenetworks:data_model`, `kubejs:fluid_tank_token`, `extendedcrafting:singularity` e tanques do Mekanism usam o **mesmo Item ID** para dezenas de materiais distintos, diferenciando-se exclusivamente pela tag NBT (`{data_model:{id:...}}`, `{Id:"extendedcrafting:..."}`, `{fluid_id:...}`).
   - **Entradas/Saídas Não-Item:** Fluidos (`mb`), Gases/Infuse Types/Slurries do Mekanism (`mb`), Energia (`FE`/`RF`) e Mana/LP aparecem como entradas e saídas obrigatórias nas cadeias de produção.

---

## 8. Estratégia Recomendada para Obter as Receitas Efetivamente Registradas

Para atender aos requisitos do projeto com máxima precisão e sem depender de adivinhação estática isolada, recomendamos uma **Estratégia em Duas Camadas (Estática Camada-a-Camada + Extração Runtime Opcional via KubeJS)**:

### Camada 1: Pipeline Estático Emulador de Camadas (Fase 2 — Funcionamento Imediato sem abrir o jogo)
Construir o importador em Python reproduzindo a **ordem exata de carregamento e transformação do modpack**:
1. **Descoberta de Tags e Unificação:**
   - Ler todas as tags de itens/fluidos/gases de `1.20.1.jar`, `mods/*.jar` e `kubejs/data/`, aplicar as mutações de `kubejs/server_scripts/tags.js` e aplicar as regras de prioridade de `config/almostunified/unify.json`.
2. **Ingestão Base (Vanilla + Mods + Configs):**
   - Carregar as 1.174 receitas vanilla + 36.953 receitas dos JARs (desempacotando wrappers `forge:conditional` e `bookshelf:item_exists` cujos mods/itens estão presentes nos 368 JARs).
   - Gerar as receitas correspondentes às 81 singularidades de `config/extendedcrafting/singularities/` e aos 44 modelos de `kubejs/data/hostilenetworks/data_models/`.
3. **Sobrescrita por Datapack (`kubejs/data/`):**
   - Aplicar os 417 arquivos de `kubejs/data/*/recipes/`: remover os 117 IDs com JSON vazio `{}` e substituir/adicionar as 300 receitas customizadas.
4. **Execução do Interpretador KubeJS (`kubejs/server_scripts/`):**
   - **Passo 4a (Remoções):** Aplicar todas as regras de `remove_recipes.js` (por `id`, `output`, `input`, `type`, `mod` e Regex).
   - **Passo 4b (Adições):** Interpretar as chamadas de `functions.js` (`create3x3`, `create3x3same`, `seedtiercrafting*`, etc.), `event.shaped`, `event.shapeless`, `event.smelting`, `event.blasting`, `event.stonecutting`, `event.smithing`, `event.custom({...})` e os 132 processos de `MMEvents.createProcesses`.
   - **Passo 4c (Substituições):** Aplicar as 119 regras de `event.replaceInput` e 2 de `event.replaceOutput` sobre o conjunto ativo de receitas.

### Camada 2: Dump de Receitas em Tempo de Execução via Script KubeJS (Sem necessidade de compilar Mod Java!)
Uma descoberta técnica fundamental desta auditoria: **como o KubeJS (`kubejs-forge-2001.6.5-build.26.jar`) já está instalado no modpack**, **não precisamos compilar um mod Java externo em Gradle** apenas para extrair o `RecipeManager` ativo do jogo!
- Podemos fornecer um pequeno script opcional em `kubejs/server_scripts/_recipe_exporter.js` (acionado por comando ou evento `ServerEvents.loaded` / final de `ServerEvents.recipes`) que acessa diretamente o `RecipeManager` do servidor Forge após o KubeJS e o Almost Unified terminarem todas as modificações, e exporta todas as receitas ativas e tags resolvidas para `kubejs/exported/active_recipes_dump.json` via `JsonIO.write(...)`.
- O nosso Importador Python (Fase 2) suportará **ambos os modos**:
  1. **Modo Estático Completo (Padrão):** Lê diretamente a pasta da instância (`mods/`, `kubejs/`, `config/`) sem precisar abrir o Minecraft.
  2. **Modo Sincronizado com Dump Runtime:** Caso o usuário abra o jogo uma vez com o script exportador ou utilize `/kubejs export`, o importador consome o dump exato do motor do jogo com 100% de fidelidade.

---

## 9. Requisitos Técnicos no Modelo de Dados (Para a Fase 2)

Com base nos arquivos reais do Project Infinity 0.1, o modelo de dados normalizado na Fase 2 **deverá obrigatoriamente suportar**:
1. **Identificadores compostos (`ItemKey`):** Além do `item_id` (ex.: `extendedcrafting:singularity` ou `hostilenetworks:prediction`), precisa suportar um discriminador canônico de NBT quando a receita exigir `forge:nbt`, `forge:partial_nbt` ou `.weakNBT()` (ex.: `extendedcrafting:singularity[Id="extendedcrafting:allthemodium_ingot"]`), caso contrário todas as 81 singularidades e 44 predições colidiriam em um único nó no grafo!
2. **Tipos de Recurso (`resource_type`):** Diferenciar `item`, `tag`, `fluid`, `gas` (incluindo `infuse_type`, `pigment`, `slurry` do Mekanism) e `energy` (`FE`).
3. **Semântica de Consumo (`chance` / `is_catalyst`):** Ingredientes com `chance == 0.0` (ou ferramentas/moldes não consumidos como `thermal:press_*_die` e malhas do `exdeorum:sieve`) devem ser marcados como `consumable: false` (catalisadores/ferramentas exigidas, mas que não multiplicam linearmente pela quantidade de lotes produzidos).
4. **Saídas Múltiplas e Probabilísticas:** Receitas como `mekanism:reaction`, `enderio:sag_milling`, `exdeorum:sieve` e `thermal:centrifuge` produzem múltiplos outputs ou outputs com probabilidade (`0.0 < chance <= 1.0`).

---

## 10. Próximos Passos Técnicos (Plano para a Fase 2)

1. **Configuração do Ambiente Python:**
   - Instalar uma versão recente do Python (ex.: Python 3.11 ou 3.12) no ambiente Windows para permitir a execução do importador e da suíte de testes automatizados (`pytest`).
2. **Definição do Modelo de Dados Padronizado (`backend/models/`):**
   - Implementar as estruturas de dados (`Recipe`, `Ingredient`, `RecipeOutput`, `MachineMetadata`, `ValidationStatus`, `DataSource`).
3. **Implementação do Pipeline de Importação (Fase 2):**
   - Módulo de Descoberta de Instância (lendo `manifest.json`, `1.20.1.jar`, `mods/*.jar`, `config/` e `kubejs/`).
   - Extrator de Tags e Resolvedor do Almost Unified.
   - Adaptadores de Formatos (Vanilla/Forge Crafting, Smelting, Extended Crafting, Avaritia, Draconic Evolution, Mekanism/EvolvedMekanism, Thermal, NuclearCraft, EnderIO, Industrial Foregoing, PneumaticCraft, AE2/AdvancedAE/CrazyAE2, Powah, Botania, Blood Magic, Mystical Agriculture, ExDeorum, BotanyPots, Singularidades e Masterful Machinery).
   - Processador de KubeJS (`kubejs/data/` overrides + `remove_recipes.js` + adições + `replace_items.js`).
   - Relatório detalhado de importação e suíte de testes automatizados (`tests/`).


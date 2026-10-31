# Arquitetura Técnica — Minecraft Crafting Explorer

## 1. Visão Geral

O **Minecraft Crafting Explorer** é projetado em camadas desacopladas para permitir a importação fiel de modpacks complexos (iniciando pelo **Project Infinity 0.1** em Minecraft 1.20.1 / Forge 47.4.28) e a extensibilidade futura para outros modpacks, versões do Minecraft e mod loaders.

A arquitetura separa estritamente:
1. **Descoberta de Arquivos (`discovery`)**: Localiza a instância, manifesto, `1.20.1.jar`, arquivos `.jar` dos mods, configs (`almostunified`, `extendedcrafting`, `mysticalcustomization`, `mm`) e scripts/datapacks (`kubejs`).
2. **Resolução de Tags e Unificação (`tags`)**: Constrói o grafo de tags (`#forge:ingots/*`, etc.) a partir do vanilla, mods, datapacks e mutações do `kubejs/server_scripts/tags.js`, aplicando a resolução de prioridade do **Almost Unified**.
3. **Adaptadores de Formatos (`adapters`)**: Interpretam e convertem mais de 40 famílias de receitas (Vanilla, Forge Conditional/Bookshelf, Extended Crafting, Avaritia, Draconic Evolution, Mekanism, Thermal, NuclearCraft, EnderIO, Industrial Foregoing, PneumaticCraft, AE2/AdvancedAE/CrazyAE2, Powah, Botania, Blood Magic, Mystical Agriculture, ExDeorum, BotanyPots, Hostile Neural Networks, Singularidades e Masterful Machinery) para o modelo normalizado.
4. **Processador de Modificações do Modpack (`kubejs_processor`)**: Aplica em ordem determinística os overrides de `kubejs/data/`, remoções de `remove_recipes.js`, adições de `server_scripts` e substituições de `replace_items.js`.
5. **Modelo de Dados Normalizado (`models`)**: Representação canônica imutável/serializável com preservação integral de dados brutos quando uma receita for parcialmente suportada ou desconhecida.
6. **Motor de Dependências (`engine` — Fase 3)**: Expansão recursiva de árvores de crafting, detecção de ciclos, consolidação de matérias-primas compartilhadas e seleção de receitas alternativas.
7. **Persistência e API (`storage` & `api` — Fase 4)**: Banco SQLite local + API REST FastAPI + Frontend React/TypeScript com React Flow.

---

## 2. Modelo de Dados Padronizado (Fase 2)

Cada receita importada é convertida para a entidade `NormalizedRecipe`:

- `recipe_id` (`str`): Identificador único completo no formato `namespace:path` (ex.: `allthemodium:allthemodium_ingot`, `mm:infinity_crucible_recipe1`).
- `recipe_type` (`str`): Tipo completo da receita (ex.: `minecraft:crafting_shaped`, `extendedcrafting:shaped_table`, `mekanism:reaction`, `mm:process`).
- `source_mod` (`str`): Namespace ou arquivo de origem responsável pela receita.
- `data_source` (`DataSource`): Enum indicando a camada de origem (`VANILLA_JAR`, `MOD_JAR`, `KUBEJS_DATAPACK`, `KUBEJS_SCRIPT`, `MOD_CONFIG`, `RUNTIME_DUMP`, `TEST_FIXTURE`).
- `source_path` (`str`): Caminho rastreável do arquivo ou entrada ZIP de onde a receita foi extraída.
- `outputs` (`list[RecipeStack]`): Lista de produtos gerados pela receita (o primeiro elemento ou o elemento marcado com `is_primary=True` é o produto principal). Suporta resultados múltiplos e probabilísticos (`chance`).
- `inputs` (`list[IngredientSlot]`): Lista de ingredientes necessários, onde cada slot contém:
  - `alternatives` (`list[RecipeStack]`): Itens, tags, fluidos, gases ou energia aceitos naquele slot.
  - `count` (`float | int`): Quantidade necessária por execução da receita.
  - `consumable` (`bool`): `True` quando consumido normalmente; `False` quando for um catalisador/molde não consumido (ex.: `chance == 0.0` no Masterful Machinery ou moldes `thermal:press_*_die`).
  - `chance` (`float`): Probabilidade de consumo (`0.0` a `1.0`).
  - `slot_key` (`str | None`): Posição ou chave na grade/máquina (ex.: `"A"`, `"center"`, `"catalyst"`, `"gas_input"`).
- `machine_info` (`MachineInfo | None`): Metadados da estação, bancada ou multibloco necessário (ex.: `station_id="mm:infinity_crucible_structure"`, `energy_fe=200000000`, `ticks=1`, `tier="CHAOTIC"`).
- `validation_status` (`ValidationStatus`):
  - `VALID`: Receita totalmente interpretada com entradas e saídas válidas.
  - `PARTIAL`: Receita reconhecida, mas com alguma condição/parâmetro especial preservado em `extra_data` / `warnings`.
  - `UNSUPPORTED`: Formato especial ou dinâmico sem entradas/saídas convencionais (ex.: `minecraft:crafting_special_*`), com `raw_data` integralmente preservado.
  - `INVALID`: Arquivo corrompido, JSON malformado ou receita vazia/incompleta.
  - `REMOVED`: Receita explicitamente desativada por override `{}` ou por `remove_recipes.js` (registrada no histórico de auditoria da importação).
- `extra_data` (`dict`): Metadados adicionais específicos da receita (padrão `pattern` da grade, condições Forge, parâmetros de temperatura/pressão).
- `raw_data` (`dict | str | None`): Dados originais preservados quando `validation_status != VALID` (ou sob demanda).
- `warnings` (`list[str]`): Avisos gerados durante a interpretação ou normalização.


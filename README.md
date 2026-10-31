# ⚡ Minecraft Crafting Explorer

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Vite](https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E)](https://vitejs.dev/)

**Minecraft Crafting Explorer** é uma ferramenta web de engenharia reversa e planejamento de produção projetada especificamente para modpacks complexos de Minecraft Java (com foco em automação técnica, progressão mágica e receitas personalizadas).

A aplicação faz a varredura direta dos arquivos `.jar`, datapacks, tags e scripts (`KubeJS`, `Almost Unified`, `CraftTweaker`), montando um grafo completo de crafting recursivo com resolução de dependências, detecção de ciclos e consolidação precisa de matérias-primas de base.

---

## ✨ Funcionalidades Principais

- 🌳 **Árvore de Crafting Recursiva Interativa:** Visualização em nós e fluxograma (via React Flow) mostrando todas as etapas intermediárias até a matéria-prima final.
- 🔍 **Busca Híbrida Inteligente:** Pesquise tanto pelo nome oficial formatado no padrão Minecraft (*ex: Blazing Crystal, Iron Ingot*) quanto pelo identificador técnico (*ex: `powah:crystal_blazing`, `minecraft:iron_ingot`*).
- ⚙️ **Identificação de Máquinas e Estações:** Mapeamento visual das máquinas de processamento com seus respectivos ícones (Energizing Orb, Altar de Sangue, Câmaras do NuclearCraft, Reatores, Prensas do Thermal, etc.).
- 🛡️ **Heurísticas Anti-Inflação & Bloqueio de Atalhos:**
  - **Filtro de Descompactação (`Compressium`):** Evita seleções de receitas recursivas de descompactação de blocos que inflavam recursos para bilhões de unidades.
  - **Bloqueio de Essências (`Mystical Agriculture`):** Toggle interativo para impedir que receitas de essências sobreponham o fluxo tecnológico autêntico de outros mods (ex: cristais do Powah!).
  - **Omissão de Recursos Triviais:** Opção para tratar recursos elementares do mundo (madeira, pedregulhos, terras) como pontos terminais, mantendo a árvore limpa.
- 📦 **Consolidação de Matérias-Primas:** Cálculo global de insumos brutos necessários para produzir qualquer quantidade desejada de um item complexo, separando catalisadores e moldes reutilizáveis.
- 🎨 **Renderização de Ícones com Alta Performance:** Servidor estático integrado capaz de servir mais de 50.000 texturas originais extraídas diretamente dos mods com latência inferior a 10ms.
- 🎯 **Gerenciamento de Objetivos de Produção:** Salve objetivos de crafting para acompanhar o progresso e marcar etapas concluídas.

---

## 🛠️ Tecnologias Utilizadas

### Backend
- **Python 3.12** com **FastAPI** & **Uvicorn**
- **SQLite** para indexação e persistência local ultrarrápida
- **Motor de Grafos e Resolução de Tags:** Interpretador nativo para Almost Unified, Forge Tags e KubeJS Server Scripts
- **Pytest** para suíte de testes de integridade e resolução de dependências

### Frontend
- **React 18** + **TypeScript**
- **Vite** para bundling otimizado
- **React Flow** para navegação e renderização de grafos
- **Lucide React** para iconografia

---

## 🚀 Instalação e Execução

### Pré-requisitos
- Python 3.10+
- Node.js 18+ (opcional, para compilar alterações no frontend)

### 1. Clonar o repositório
```bash
git clone https://github.com/SEU-USUARIO/MinecraftTreeViewer.git
cd MinecraftTreeViewer
```

### 2. Configurar o ambiente Python
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / MacOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Executar o servidor
```bash
python -m uvicorn backend.api.server:app --host 0.0.0.0 --port 8000
```
Acesse a aplicação no navegador em: **`http://localhost:8000`**

---

## 🏗️ Arquitetura

O projeto adota uma arquitetura desacoplada em pipeline:

1. **Discovery:** Localização e auditoria da instância do Minecraft e seus JARs.
2. **Tag Resolution:** Mapeamento unificado de tags com suporte a Almost Unified.
3. **Adapters:** Normalização de mais de 40 formatos de receitas de mods em um schema canônico (`NormalizedRecipe`).
4. **KubeJS Processor:** Aplicação determinística de overrides, adições e remoções de receitas customizadas.
5. **Dependency Engine:** Travessia de grafo, heurística de caminhos ótimos e detecção de dependência circular.
6. **API / Presentation:** Camada REST e interface interativa com dados reativos.

---

## 📄 Licença

Distribuído sob a licença MIT. Consulte `LICENSE` para mais informações.
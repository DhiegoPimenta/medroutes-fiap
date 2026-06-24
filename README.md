# MedRoutes 🚑

> **Tech Challenge — Fase 2 | IA para Devs | FIAP PosTech**
> Projeto 2: Otimização de Rotas para Distribuição de Medicamentos e Insumos

Sistema completo de otimização de rotas para distribuição de medicamentos e insumos hospitalares. Resolve o **Vehicle Routing Problem (VRP)** com um **Algoritmo Genético implementado do zero**, visualiza as rotas em mapa interativo e usa a **API da Anthropic (Claude Sonnet)** para gerar instruções para motoristas, relatórios de eficiência e responder perguntas em linguagem natural.

🌐 **Demo em produção:** https://ca-medroutes.ambitiousstone-87ab2c0d.eastus2.azurecontainerapps.io

---

## Índice

- [Contexto e objetivo](#contexto-e-objetivo)
- [Como funciona — fluxo completo](#como-funciona--fluxo-completo)
- [Algoritmo Genético — detalhes técnicos](#algoritmo-genético--detalhes-técnicos)
- [Integração com Claude (LLM)](#integração-com-claude-llm)
- [Experimentos comparativos](#experimentos-comparativos)
- [Stack tecnológica](#stack-tecnológica)
- [Arquitetura do sistema](#arquitetura-do-sistema)
- [Infraestrutura no Azure (IaC com Bicep)](#infraestrutura-no-azure-iac-com-bicep)
- [CI/CD — GitHub Actions](#cicd--github-actions)
- [Como rodar localmente](#como-rodar-localmente)
- [Como rodar os testes](#como-rodar-os-testes)
- [Como rodar os experimentos](#como-rodar-os-experimentos)
- [Como fazer deploy no Azure](#como-fazer-deploy-no-azure)
- [Estrutura de pastas](#estrutura-de-pastas)
- [Limitações conhecidas](#limitações-conhecidas)

---

## Contexto e objetivo

Um sistema hospitalar precisa entregar medicamentos críticos e insumos regulares para múltiplos endereços, usando uma frota de veículos com capacidade de carga e autonomia máxima definidas. O problema é uma variante do clássico **Travelling Salesman Problem (TSP)** estendido para múltiplos veículos: o **VRP (Vehicle Routing Problem)**.

**Desafios reais modelados:**
- Medicamentos críticos devem ser entregues **antes** de insumos regulares na mesma rota.
- Veículos têm **capacidade de carga máxima** (kg) e **autonomia máxima** (km).
- A frota pode ter **múltiplos veículos** simultaneamente.
- As rotas devem partir e retornar ao **depósito central**.

**Objetivo:** minimizar a distância total percorrida pela frota, respeitando todas as restrições, priorizando entregas críticas.

---

## Como funciona — fluxo completo

```
Usuário define:
  ├── Endereço do depósito (origem/retorno de todas as rotas)
  ├── Lista de entregas (endereço, tipo, peso)
  └── Configuração da frota (nº de veículos, capacidade, autonomia)
         │
         ▼
Geocodificação (Nominatim/OpenStreetMap)
  └── Converte endereços em coordenadas (lat, lon)
         │
         ▼
Algoritmo Genético (VRP)
  ├── Inicializa população de rotas aleatórias
  ├── Evolui por N gerações (seleção → crossover → mutação → elitismo)
  └── Retorna melhor rota encontrada + histórico de convergência
         │
         ▼
Visualização (Folium + Leaflet)
  └── Mapa interativo com rotas por veículo em cores diferentes
         │
         ▼
Assistente Claude (Anthropic API)
  ├── Instruções detalhadas por motorista
  ├── Relatório de eficiência (comparativo com baseline aleatório)
  └── Q&A em linguagem natural sobre as rotas
```

### Interface Streamlit (passo a passo)

1. **Sidebar — Depósito:** informe o endereço de origem (ex.: `Av. Paulista, 1000, São Paulo`).
2. **Sidebar — Entregas:** adicione entregas com endereço, tipo (`Medicamento crítico` ou `Insumo regular`) e peso.
3. **Sidebar — Veículos:** configure número de veículos, capacidade de carga (kg) e autonomia (km).
4. **Painel principal — Otimizar rotas:** ajuste os hiperparâmetros do AG (população, gerações, taxa de mutação) e clique em **Otimizar rotas**.
5. **Resultado:** distância total, veículos utilizados, tempo de otimização e mapa interativo.
6. **Assistente Claude:** três abas — instruções por motorista, relatório de eficiência e Q&A.

---

## Algoritmo Genético — detalhes técnicos

Implementado **do zero** em `app/genetic/`, sem bibliotecas de AG (DEAP ou similares), conforme exigido pelo desafio.

### Representação cromossômica — Giant Tour

O cromossomo é uma **permutação de índices** de todas as entregas. Exemplo com 5 entregas e 2 veículos:

```
Cromossomo: [2, 0, 4, 1, 3]
             ↑  ↑  ↑  ↑  ↑
        índices das entregas em ordem de visita

Decodificação (greedy por capacidade):
  Veículo 0: entrega[2] → entrega[0] → entrega[4]  (até encher capacidade)
  Veículo 1: entrega[1] → entrega[3]               (resto)
```

**Por que Giant Tour?** Permite reutilizar operadores clássicos de permutação (OX, inversão) sem inventar operadores específicos para múltiplas rotas, mantendo a implementação simples, correta e bem testada.

### Decodificação (`decode_chromosome`)

Percorre a permutação e distribui entregas entre veículos respeitando a capacidade de carga. Se um veículo não comporta a próxima entrega, avança para o próximo. Violações são penalizadas na função fitness.

### Operadores genéticos (`app/genetic/operators.py`)

| Operador | Implementação | Descrição |
|---|---|---|
| **Seleção por torneio** | `tournament_selection` | Sorteia `tournament_size` indivíduos, seleciona o de menor fitness. Controla pressão seletiva. |
| **Crossover OX** | `order_crossover` | Copia segmento contíguo de um pai; preenche o restante com genes do outro pai na ordem que aparecem. Garante permutação válida. |
| **Mutação por inversão** | `inversion_mutation` | Inverte um subtrecho aleatório do cromossomo com probabilidade `mutation_rate`. Preserva validade. |
| **Elitismo** | no loop principal | Os `elitism_count` melhores indivíduos são copiados integralmente para a próxima geração. Fitness nunca piora entre gerações. |

### Função fitness (`evaluate_fitness`)

**Minimização** — quanto menor, melhor. Composta por 4 termos ponderados:

```
fitness = w_dist × distância_total
        + w_prioridade × penalidade_prioridade
        + w_capacidade × kg_excedentes
        + w_autonomia  × km_excedentes
```

| Componente | Peso padrão | O que mede |
|---|---|---|
| `distância_total` | 1.0 | Soma das distâncias Haversine de todas as rotas (depósito → paradas → depósito) |
| `penalidade_prioridade` | 5.0 | Posição normalizada de entregas críticas na rota (incentiva entregá-las primeiro) |
| `penalidade_capacidade` | 1000.0 | Kg excedentes acima da capacidade do veículo (fortemente penalizado) |
| `penalidade_autonomia` | 1000.0 | Km excedentes acima da autonomia do veículo (fortemente penalizado) |

### Cálculo de distância — Haversine

```python
def haversine_distance_km(coord_a, coord_b):
    # considera a curvatura da Terra
    # adequado para distâncias urbanas em linha reta
    # resultado em quilômetros
```

### Hiperparâmetros configuráveis (`GeneticAlgorithmConfig`)

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `population_size` | 80 | Número de indivíduos por geração |
| `num_generations` | 150 | Número de gerações |
| `mutation_rate` | 0.15 | Probabilidade de mutação por inversão |
| `tournament_size` | 3 | Tamanho do torneio na seleção |
| `elitism_count` | 2 | Indivíduos preservados por elitismo |
| `random_seed` | None | Semente para reprodutibilidade |

---

## Integração com Claude (LLM)

Implementada em `app/llm/claude_client.py` usando o **SDK oficial da Anthropic**.

**Modelo:** `claude-sonnet-4-6` (configurável via variável de ambiente `ANTHROPIC_MODEL`)

### Funcionalidades

#### 1. Instruções por motorista (`generate_driver_instructions`)

Gera em português, para cada veículo:
- Ordem das paradas com endereço e peso
- Alertas em destaque para medicamentos críticos
- Lembrete de retorno ao depósito

**Prompt de sistema:**
> "Você é um assistente de logística que escreve instruções claras, objetivas e amigáveis para motoristas de entrega de medicamentos e insumos hospitalares."

#### 2. Relatório de eficiência (`generate_efficiency_report`)

Compara a rota otimizada com um baseline aleatório e gera parágrafo executivo com:
- Distância otimizada vs. baseline
- Economia em km e %
- Número de veículos e entregas críticas

**Prompt de sistema:**
> "Você é um analista de logística que resume métricas de eficiência de roteamento de forma clara para gestores não técnicos."

#### 3. Q&A sobre as rotas (`answer_question_about_routes`)

Responde perguntas em linguagem natural como:
- *"Qual entrega é mais urgente?"*
- *"Qual veículo está mais sobrecarregado?"*
- *"Quantas entregas críticas temos?"*

Contexto injetado no prompt: resumo de cada veículo com entregas, peso atual vs. capacidade, distância vs. autonomia.

### Segurança da chave

A `ANTHROPIC_API_KEY` é lida **exclusivamente** de variável de ambiente — nunca hardcoded. Em produção, é lida do **Azure Key Vault** via Managed Identity.

---

## Experimentos comparativos

Executados via `experiments/run_experiments.py` sobre cenário sintético fixo: **25 entregas, 4 veículos, 120 gerações**, mesmo `random_seed=42` para comparação justa.

### Resultados

| Config | Descrição | Pop. | Mutação | Torneio | Fitness | Dist. (km) | Tempo (s) | Melhor geração |
|---|---|---|---|---|---|---|---|---|
| **A** | Pop. pequena, mutação baixa | 30 | 0.05 | 3 | 5490.37 | 305.71 | 0.47 | 115 |
| **B** | Pop. grande, mutação baixa | 150 | 0.05 | 3 | 358.64 | 265.13 | 2.25 | 82 |
| **C** ⭐ | Pop. média, mutação alta | 80 | 0.40 | 3 | **322.75** | **234.41** | **1.23** | 87 |
| **D** | Pop. média, torneio maior | 80 | 0.10 | 6 | 330.84 | 241.44 | 1.62 | 90 |

### Conclusões

- **Config A** convergiu para um ótimo local muito ruim — população pequena limita diversidade genética e mutação baixa não compensa, resultando em fitness ~17× pior.
- **Config C** obteve o **melhor resultado**: mutação alta (0.40) ajuda a escapar de ótimos locais sem exigir população grande. Melhor custo-benefício.
- **Config B** chegou perto do ótimo, mas com quase 2× o tempo de Config C — retornos decrescentes de aumentar população com mutação baixa.
- **Melhor configuração para produção:** população média (80) + mutação alta (0.40) + torneio padrão (3).

---

## Stack tecnológica

### Backend / Core

| Tecnologia | Versão | Função |
|---|---|---|
| **Python** | 3.11 | Linguagem principal |
| **Poetry** | latest | Gerenciamento de dependências e ambiente virtual |
| **Streamlit** | ^1.38 | Interface web interativa |
| **Folium** | ^0.17 | Visualização de mapas (Leaflet.js) |
| **streamlit-folium** | ^0.23 | Integração Folium ↔ Streamlit |
| **geopy** | ^2.4 | Geocodificação via Nominatim/OpenStreetMap |
| **anthropic** | ^0.54 | SDK oficial da Anthropic para Claude API |
| **pandas** | ^2.2 | Manipulação de dados tabulares |
| **numpy** | ^1.26 | Operações numéricas |
| **pydantic** | ^2.8 | Validação de modelos de dados |
| **python-dotenv** | ^1.0 | Leitura de variáveis de ambiente (.env) |

### LLM

| Serviço | Modelo | Uso |
|---|---|---|
| **Anthropic Claude API** | `claude-sonnet-4-6` | Instruções por motorista, relatório de eficiência, Q&A |

### Geocodificação

| Serviço | Protocolo | Custo |
|---|---|---|
| **Nominatim (OpenStreetMap)** | HTTP REST | Gratuito (limite: ~1 req/s) |

### Testes

| Ferramenta | Versão | Uso |
|---|---|---|
| **pytest** | ^8.3 | Framework de testes |
| **pytest-mock** | ^3.14 | Mock de dependências externas |
| **pytest-cov** | ^5.0 | Cobertura de código |

### Infraestrutura e DevOps

| Tecnologia | Uso |
|---|---|
| **Docker** | Containerização da aplicação Streamlit |
| **Azure Container Registry (ACR)** | Repositório privado de imagens Docker |
| **Azure Container Apps** | Plataforma serverless para execução do container |
| **Azure Key Vault** | Armazenamento seguro da ANTHROPIC_API_KEY |
| **Azure Managed Identity** | Autenticação sem credenciais entre serviços Azure |
| **Azure Log Analytics** | Coleta e análise de logs do Container App |
| **Bicep** | IaC (Infrastructure as Code) para provisionamento Azure |
| **GitHub Actions** | CI/CD: testes → build Docker → deploy automático |

---

## Arquitetura do sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    Usuário (browser)                        │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Azure Container Apps                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Streamlit (porta 8501)                  │   │
│  │                                                      │   │
│  │  ┌──────────────┐    ┌──────────────────────────┐   │   │
│  │  │  Interface   │    │   Algoritmo Genético     │   │   │
│  │  │  (main.py)   │───▶│   (genetic/)             │   │   │
│  │  └──────┬───────┘    └──────────────────────────┘   │   │
│  │         │                                            │   │
│  │  ┌──────▼───────┐    ┌──────────────────────────┐   │   │
│  │  │  Geocoding   │───▶│   Nominatim API          │   │   │
│  │  │  (geopy)     │    │   (OpenStreetMap)         │   │   │
│  │  └──────┬───────┘    └──────────────────────────┘   │   │
│  │         │                                            │   │
│  │  ┌──────▼───────┐    ┌──────────────────────────┐   │   │
│  │  │ Claude Client│───▶│   Anthropic API          │   │   │
│  │  │  (llm/)      │    │   claude-sonnet-4-6       │   │   │
│  │  └──────┬───────┘    └──────────────────────────┘   │   │
│  │         │                                            │   │
│  │  ┌──────▼───────┐                                   │   │
│  │  │  Folium Map  │                                   │   │
│  │  │  (maps/)     │                                   │   │
│  │  └──────────────┘                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Managed Identity ──▶ Key Vault (ANTHROPIC_API_KEY)        │
│  Managed Identity ──▶ Container Registry (pull imagem)     │
└─────────────────────────────────────────────────────────────┘
```

---

## Infraestrutura no Azure (IaC com Bicep)

Toda a infraestrutura está definida em `infra/` e pode ser provisionada com um único comando.

### Recursos criados

| Recurso | Nome | Função |
|---|---|---|
| Resource Group | `rg-medroutes` | Agrupa todos os recursos |
| Container Registry | `acrmedroutes<hash>.azurecr.io` | Armazena a imagem Docker |
| User-Assigned Managed Identity | `id-medroutes` | Autentica no ACR e Key Vault sem senhas |
| Key Vault | `kv-mdr-fiap-tc2` | Guarda `ANTHROPIC_API_KEY` com segurança |
| Log Analytics Workspace | `log-medroutes` | Coleta logs do Container App |
| Container Apps Environment | `cae-medroutes` | Ambiente gerenciado para containers |
| Container App | `ca-medroutes` | Executa o Streamlit (1–3 réplicas) |

### Decisões de segurança

- **Sem admin user no ACR:** autenticação via Managed Identity com role `AcrPull`.
- **Key Vault com RBAC habilitado:** a API key é lida pelo Container App via Managed Identity (role `Key Vault Secrets User`) — nunca em texto plano.
- **Purge protection ativado no Key Vault:** proteção contra deleção acidental.
- **Soft delete habilitado:** recuperação de segredos por 90 dias.

### Estrutura dos arquivos Bicep

```
infra/
├── main.bicep        # Escopo: subscription — cria o Resource Group e chama o módulo
├── resources.bicep   # Escopo: resource group — cria todos os recursos acima
├── parameters.json   # Parâmetros de deploy (sem valores sensíveis)
└── deploy.ps1        # Script PowerShell de deploy manual (Windows)
```

### Parâmetros do deploy

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `environmentName` | `medroutes` | Prefixo dos recursos |
| `location` | `eastus2` | Região do Azure |
| `resourceGroupName` | `rg-medroutes` | Nome do Resource Group |
| `anthropicApiKey` | — | Chave da API (armazenada no Key Vault) |
| `anthropicModel` | `claude-sonnet-4-6` | Modelo Claude |

---

## CI/CD — GitHub Actions

Pipeline em `.github/workflows/deploy.yml` com dois jobs:

### Job 1: `test`
- Instala Python 3.11 + Poetry
- Roda `pytest tests/ -v`
- **Bloqueia o deploy se qualquer teste falhar**

### Job 2: `deploy` (apenas na branch `main`/`master`, após `test` passar)
1. Login no Azure via Service Principal
2. Aplica infraestrutura Bicep (`az deployment sub create`)
3. Obtém o login server do ACR
4. Habilita admin temporário no ACR, faz login Docker, desabilita após o push
5. `docker build` + `docker push` da imagem com tag `<git-sha>` e `latest`
6. `az containerapp update` com a nova imagem

**Secrets necessários no repositório GitHub:**

| Secret | Descrição |
|---|---|
| `AZURE_CLIENT_ID` | Client ID do Service Principal |
| `AZURE_CLIENT_SECRET` | Client Secret do Service Principal |
| `AZURE_TENANT_ID` | Tenant ID do Azure AD |
| `AZURE_SUBSCRIPTION_ID` | ID da subscription |
| `ANTHROPIC_API_KEY` | Chave da API da Anthropic |

---

## Como rodar localmente

### Pré-requisitos

- Python 3.10+
- [Poetry](https://python-poetry.org/docs/#installation)
- Chave da API da Anthropic (obtenha em https://console.anthropic.com)

### Instalação

```bash
git clone https://github.com/DhiegoPimenta/medroutes-fiap.git
cd medroutes-fiap

# instala dependências
poetry install

# cria o arquivo de variáveis de ambiente
cp .env.example .env
```

Edite o `.env` e preencha a chave:

```env
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
NOMINATIM_USER_AGENT=medroutes-fiap-tech-challenge
```

### Executar

```bash
poetry run streamlit run app/main.py
```

Acesse `http://localhost:8501`.

### Exemplo de cenário de teste

| Campo | Valor |
|---|---|
| Depósito | `Av. Paulista, 1000, São Paulo` |
| Entrega 1 | `Rua da Consolação, 500, São Paulo` — Crítico — 2 kg |
| Entrega 2 | `Av. Rebouças, 1200, São Paulo` — Regular — 8 kg |
| Entrega 3 | `Rua Augusta, 800, São Paulo` — Crítico — 1.5 kg |
| Entrega 4 | `Av. Brigadeiro Faria Lima, 2000, São Paulo` — Regular — 12 kg |
| Entrega 5 | `Rua Oscar Freire, 300, São Paulo` — Crítico — 0.5 kg |
| Veículo 1 | Capacidade: 15 kg — Autonomia: 50 km |
| Veículo 2 | Capacidade: 20 kg — Autonomia: 80 km |

---

## Como rodar os testes

```bash
poetry run pytest tests/ -v
```

### Cobertura de testes (35 testes)

| Arquivo | O que testa |
|---|---|
| `tests/test_fitness.py` | Haversine, `decode_chromosome`, `evaluate_fitness` (capacidade, prioridade) |
| `tests/test_operators.py` | `tournament_selection`, `order_crossover` (validade da permutação), `inversion_mutation` |
| `tests/test_algorithm.py` | Execução completa do AG, monotonicidade do fitness com elitismo |
| `tests/test_models.py` | Validações das dataclasses (`Delivery`, `Vehicle`, `RoutingProblem`) |
| `tests/test_geocoding.py` | Serviço de geocodificação com mock do Nominatim (sem chamadas reais) |
| `tests/test_claude_client.py` | Integração Claude mockada (sem custo ou dependência de rede) |

---

## Como rodar os experimentos

```bash
poetry run python experiments/run_experiments.py
```

Gera em `experiments/results/`:
- `comparison.csv` — tabela com métricas de todas as configurações
- `convergence.png` — gráfico de convergência por configuração

---

## Como fazer deploy no Azure

### Pré-requisitos

- Azure CLI instalado e autenticado (`az login --tenant <tenant>`)
- Permissão de `Contributor` na subscription

### Deploy manual (Windows)

```powershell
cd medroutes-fiap
$env:ANTHROPIC_API_KEY = "sk-ant-..."
.\infra\deploy.ps1
```

O script executa:
1. `az deployment sub what-if` — valida sem aplicar (pede confirmação)
2. `az deployment sub create` — aplica o Bicep
3. `az acr build` — builda a imagem no ACR (sem Docker local)
4. `az containerapp update` — atualiza o Container App

### Deploy via GitHub Actions

Basta fazer push na branch `main` ou `master`. O pipeline roda automaticamente.

---

## Estrutura de pastas

```
medroutes/
├── app/
│   ├── main.py                  # Streamlit entry point
│   ├── geocoding.py             # Geocodificação via Nominatim
│   ├── genetic/
│   │   ├── algorithm.py         # GeneticAlgorithm — loop principal, elitismo
│   │   ├── operators.py         # tournament_selection, order_crossover, inversion_mutation
│   │   └── fitness.py           # decode_chromosome, evaluate_fitness, haversine
│   ├── llm/
│   │   └── claude_client.py     # ClaudeClient — instruções, relatório, Q&A
│   ├── maps/
│   │   └── route_map.py         # Mapa Folium com rotas por veículo
│   └── models/
│       └── delivery.py          # Dataclasses: Delivery, Vehicle, DepotLocation, RoutingProblem
├── experiments/
│   ├── run_experiments.py       # 4 configurações comparativas do AG
│   └── results/                 # CSV + gráfico de convergência (gerados)
├── infra/
│   ├── main.bicep               # Entry point Bicep (escopo subscription)
│   ├── resources.bicep          # Recursos do Resource Group
│   ├── parameters.json          # Parâmetros de deploy
│   └── deploy.ps1               # Script de deploy manual (Windows/PowerShell)
├── tests/                       # 35 testes pytest
├── .github/workflows/
│   └── deploy.yml               # Pipeline CI/CD
├── Dockerfile                   # Imagem Python 3.11 slim + Poetry
├── pyproject.toml               # Dependências e configuração Poetry
├── .env.example                 # Template de variáveis de ambiente
└── README.md
```

---

## Limitações conhecidas

- **Geocodificação lenta:** Nominatim tem limite de ~1 req/s; muitas entregas cadastradas de uma vez podem demorar.
- **Distância em linha reta:** Haversine não considera vias reais, trânsito ou semáforos — adequado para o escopo do desafio.
- **Decodificação greedy:** a distribuição de entregas entre veículos usa heurística greedy, não split ótimo via programação dinâmica.
- **Sem janela de tempo:** o modelo atual não suporta restrições de horário de entrega.
- **Estado em memória:** o Streamlit não persiste dados entre sessões — cada reload reinicia o cadastro.

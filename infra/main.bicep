// =============================================================================
// MedRoutes - main.bicep (escopo de subscription)
//
// Ponto de entrada da infraestrutura. Cria o Resource Group e delega a
// criacao dos demais recursos (ACR, Container Apps Environment, Container
// App, Key Vault, Log Analytics, identidade gerenciada) ao modulo
// resources.bicep, que roda no escopo do Resource Group.
//
// Decisoes de seguranca (seguindo Azure best practices):
//   - Autenticacao no ACR via Managed Identity (sem usuario admin/chaves).
//   - ANTHROPIC_API_KEY armazenada no Key Vault, nunca em texto plano no
//     Bicep ou em variavel de ambiente commitada.
//   - Key Vault com RBAC habilitado e purge protection ativado (nao
//     desabilitar, mesmo em ambiente de estudo/demo).
// =============================================================================

targetScope = 'subscription'

@description('Nome do ambiente (usado como prefixo/sufixo dos recursos, ex.: dev, prod).')
param environmentName string = 'medroutes'

@description('Regiao do Azure onde os recursos serao criados.')
param location string = 'brazilsouth'

@description('Nome do Resource Group a ser criado.')
param resourceGroupName string = 'rg-${environmentName}'

@description('Chave da API da Anthropic (Claude). Sera armazenada no Key Vault, nunca em texto plano.')
@secure()
param anthropicApiKey string = ''

@description('Modelo Claude utilizado pela aplicacao.')
param anthropicModel string = 'claude-sonnet-4-6'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
  tags: {
    project: 'medroutes'
    environment: environmentName
  }
}

module resources 'resources.bicep' = {
  name: 'medroutes-resources'
  scope: resourceGroup
  params: {
    environmentName: environmentName
    location: location
    anthropicApiKey: anthropicApiKey
    anthropicModel: anthropicModel
  }
}

output resourceGroupName string = resourceGroup.name
output containerRegistryLoginServer string = resources.outputs.containerRegistryLoginServer
output containerAppFqdn string = resources.outputs.containerAppFqdn
output containerAppUrl string = resources.outputs.containerAppUrl

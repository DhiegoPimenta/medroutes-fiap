// =============================================================================
// MedRoutes - resources.bicep (escopo de resource group)
//
// Recursos criados:
//   1. Log Analytics Workspace        -> logs do Container Apps Environment
//   2. Azure Container Registry (ACR) -> guarda a imagem Docker do app
//   3. User-Assigned Managed Identity -> autentica ACR e Key Vault sem chaves
//   4. Key Vault                      -> guarda ANTHROPIC_API_KEY com seguranca
//   5. Container Apps Environment     -> ambiente gerenciado para o Container App
//   6. Container App                  -> roda o Streamlit (MedRoutes)
// =============================================================================

@description('Nome do ambiente, usado para compor nomes unicos de recursos.')
param environmentName string

@description('Regiao do Azure.')
param location string

@secure()
@description('Chave da API da Anthropic. Vazia = recurso de Key Vault criado sem valor (definir depois via az keyvault secret set).')
param anthropicApiKey string = ''

@description('Modelo Claude utilizado pela aplicacao.')
param anthropicModel string

@description('Tag/versao da imagem do container a ser implantada.')
param containerImageTag string = 'latest'

// sufixo curto e deterministico para garantir nomes globais unicos (ACR e Key Vault)
var uniqueSuffix = uniqueString(resourceGroup().id)
var acrName = toLower(replace('acr${environmentName}${uniqueSuffix}', '-', ''))
var keyVaultName = toLower('kv-${environmentName}-${take(uniqueSuffix, 6)}')
var logAnalyticsName = 'log-${environmentName}'
var containerAppEnvName = 'cae-${environmentName}'
var containerAppName = 'ca-${environmentName}'
var identityName = 'id-${environmentName}'
var containerPort = 8501

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Identidade gerenciada usada pelo Container App para autenticar no ACR
// (AcrPull) e no Key Vault (Key Vault Secrets User), sem credenciais em texto plano.
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: location
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false // autenticacao apenas via Managed Identity/RBAC
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

@description('Role "AcrPull": permite extrair (pull) imagens do registry.')
resource acrPullRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, managedIdentity.id, 'AcrPull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleDefinition.id
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true // nunca desabilitar (orientacao de seguranca)
  }
}

resource anthropicSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: keyVault
  name: 'anthropic-api-key'
  properties: {
    value: empty(anthropicApiKey) ? 'PLACEHOLDER-DEFINA-VIA-AZ-CLI' : anthropicApiKey
  }
}

@description('Role "Key Vault Secrets User": permite leitura de segredos (sem gerenciar o cofre).')
resource keyVaultSecretsUserRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, 'KeyVaultSecretsUser')
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinition.id
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: containerAppEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: containerPort
        allowInsecure: false
        transport: 'auto'
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: [
        {
          name: 'anthropic-api-key'
          keyVaultUrl: anthropicSecret.properties.secretUri
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'medroutes'
          image: '${containerRegistry.properties.loginServer}/medroutes:${containerImageTag}'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            {
              name: 'ANTHROPIC_API_KEY'
              secretRef: 'anthropic-api-key'
            }
            {
              name: 'ANTHROPIC_MODEL'
              value: anthropicModel
            }
            {
              name: 'NOMINATIM_USER_AGENT'
              value: 'medroutes-fiap-tech-challenge'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/_stcore/health'
                port: containerPort
              }
              initialDelaySeconds: 15
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
  dependsOn: [
    acrPullRoleAssignment
    keyVaultRoleAssignment
  ]
}

output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output managedIdentityClientId string = managedIdentity.properties.clientId
output keyVaultName string = keyVault.name

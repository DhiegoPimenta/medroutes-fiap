# =============================================================================
# deploy.ps1 - Deploy do MedRoutes no Azure Container Apps (sem Docker local)
#
# Usa az acr build para buildar a imagem direto no Azure Container Registry,
# sem precisar do Docker instalado na maquina.
#
# Pre-requisitos:
#   - Azure CLI instalado e autenticado (az login)
#   - Permissao de Contributor na subscription
#
# Uso:
#   $env:ANTHROPIC_API_KEY = "sk-ant-xxx"
#   cd "C:\Users\dhieg\Claude\Projects\IADT - Fase 2 - Tech challenge\medroutes"
#   .\infra\deploy.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

$ENVIRONMENT_NAME  = if ($env:ENVIRONMENT_NAME)   { $env:ENVIRONMENT_NAME }   else { "medroutes" }
$LOCATION          = if ($env:LOCATION)            { $env:LOCATION }           else { "eastus2" }
$RESOURCE_GROUP    = if ($env:RESOURCE_GROUP_NAME) { $env:RESOURCE_GROUP_NAME } else { "rg-$ENVIRONMENT_NAME" }
$ANTHROPIC_API_KEY = if ($env:ANTHROPIC_API_KEY)   { $env:ANTHROPIC_API_KEY }   else { "" }
$DEPLOYMENT_NAME   = "medroutes-$(Get-Date -Format 'yyyyMMddHHmmss')"
$SUBSCRIPTION_ID   = "a09cd1e5-d2ef-4d8e-97e2-83082370a865"

# garante que rodamos da raiz do projeto
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptDir "..")

Write-Host "=============================================" -ForegroundColor Magenta
Write-Host "  MedRoutes - Deploy Azure Container Apps   " -ForegroundColor Magenta
Write-Host "=============================================" -ForegroundColor Magenta
Write-Host "  Subscription : $SUBSCRIPTION_ID"
Write-Host "  Resource Group: $RESOURCE_GROUP"
Write-Host "  Location      : $LOCATION"
Write-Host "  Deployment    : $DEPLOYMENT_NAME"
Write-Host ""

if (-not $ANTHROPIC_API_KEY) {
    Write-Warning "ANTHROPIC_API_KEY nao definida. A chave sera definida como PLACEHOLDER no Key Vault."
    Write-Warning "Defina depois com: az keyvault secret set --vault-name <kv> --name anthropic-api-key --value <chave>"
}

# garante subscription correta
az account set --subscription $SUBSCRIPTION_ID

# ─── 1. what-if ──────────────────────────────────────────────────────────────
Write-Host "`n[1/5] Validando template Bicep (what-if)..." -ForegroundColor Cyan
az deployment sub what-if `
    --name $DEPLOYMENT_NAME `
    --location $LOCATION `
    --template-file infra/main.bicep `
    --parameters environmentName=$ENVIRONMENT_NAME `
                 location=$LOCATION `
                 resourceGroupName=$RESOURCE_GROUP `
                 anthropicApiKey=$ANTHROPIC_API_KEY

$confirm = Read-Host "`nContinuar com o deploy? (s/N)"
if ($confirm -notin @("s","S")) {
    Write-Host "Deploy cancelado." -ForegroundColor Yellow
    exit 0
}

# ─── 2. apply bicep ──────────────────────────────────────────────────────────
Write-Host "`n[2/5] Aplicando template Bicep..." -ForegroundColor Cyan
az deployment sub create `
    --name $DEPLOYMENT_NAME `
    --location $LOCATION `
    --template-file infra/main.bicep `
    --parameters environmentName=$ENVIRONMENT_NAME `
                 location=$LOCATION `
                 resourceGroupName=$RESOURCE_GROUP `
                 anthropicApiKey=$ANTHROPIC_API_KEY

# captura outputs do deployment
$ACR_LOGIN_SERVER = az deployment sub show `
    --name $DEPLOYMENT_NAME `
    --query "properties.outputs.containerRegistryLoginServer.value" -o tsv

$ACR_NAME = $ACR_LOGIN_SERVER.Split(".")[0]

Write-Host "`n  ACR criado: $ACR_LOGIN_SERVER" -ForegroundColor Green

# ─── 3. habilita admin temporariamente para az acr build ─────────────────────
Write-Host "`n[3/5] Habilitando admin temporario no ACR para build remoto..." -ForegroundColor Cyan
az acr update --name $ACR_NAME --admin-enabled true --resource-group $RESOURCE_GROUP | Out-Null

# ─── 4. build remoto via az acr build (sem Docker local) ─────────────────────
Write-Host "`n[4/5] Buildando imagem no Azure (az acr build - sem Docker local)..." -ForegroundColor Cyan
az acr build `
    --registry $ACR_NAME `
    --image "medroutes:latest" `
    --resource-group $RESOURCE_GROUP `
    .

# desabilita admin apos o build (seguranca)
az acr update --name $ACR_NAME --admin-enabled false --resource-group $RESOURCE_GROUP | Out-Null
Write-Host "  Admin ACR desabilitado novamente (Managed Identity ativa)." -ForegroundColor Green

# ─── 5. atualiza container app com a nova imagem ─────────────────────────────
Write-Host "`n[5/5] Atualizando Container App com a nova imagem..." -ForegroundColor Cyan
$CONTAINER_APP_NAME = "ca-$ENVIRONMENT_NAME"
az containerapp update `
    --name $CONTAINER_APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --image "${ACR_LOGIN_SERVER}/medroutes:latest"

# captura URL final
$APP_URL = az deployment sub show `
    --name $DEPLOYMENT_NAME `
    --query "properties.outputs.containerAppUrl.value" -o tsv

Write-Host "`n=============================================" -ForegroundColor Green
Write-Host "  Deploy concluido com sucesso!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  URL da aplicacao  : $APP_URL" -ForegroundColor Green
Write-Host "  Portal Azure      : https://portal.azure.com/#@/resource/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/overview" -ForegroundColor Green
Write-Host ""
Write-Host "  Para ver os logs em tempo real:" -ForegroundColor Yellow
Write-Host "  az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --follow" -ForegroundColor Yellow

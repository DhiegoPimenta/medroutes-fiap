#!/usr/bin/env bash
# =============================================================================
# Script de deploy do MedRoutes no Azure Container Apps.
#
# Pre-requisitos:
#   - Azure CLI instalado e autenticado (`az login`)
#   - Docker instalado e em execucao
#   - Permissao de Contributor + User Access Administrator na subscription
#     (necessario para criar role assignments de Managed Identity)
#
# Uso:
#   ANTHROPIC_API_KEY=sk-ant-xxx ./infra/deploy.sh
# =============================================================================

set -euo pipefail

ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-medroutes}"
LOCATION="${LOCATION:-brazilsouth}"
RESOURCE_GROUP_NAME="${RESOURCE_GROUP_NAME:-rg-${ENVIRONMENT_NAME}}"
DEPLOYMENT_NAME="medroutes-$(date +%Y%m%d%H%M%S)"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "Aviso: ANTHROPIC_API_KEY nao definida. A aplicacao subira sem chave da Claude API."
  echo "Voce pode definir depois com: az keyvault secret set --vault-name <nome-do-kv> --name anthropic-api-key --value <chave>"
fi

echo "1/4 - Validando o template Bicep com 'what-if' (subscription scope)..."
az deployment sub what-if \
  --name "$DEPLOYMENT_NAME" \
  --location "$LOCATION" \
  --template-file infra/main.bicep \
  --parameters environmentName="$ENVIRONMENT_NAME" location="$LOCATION" resourceGroupName="$RESOURCE_GROUP_NAME" anthropicApiKey="${ANTHROPIC_API_KEY:-}"

read -p "Continuar com o deploy da infraestrutura? (s/N) " confirm
if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
  echo "Deploy cancelado."
  exit 0
fi

echo "2/4 - Aplicando o template Bicep..."
az deployment sub create \
  --name "$DEPLOYMENT_NAME" \
  --location "$LOCATION" \
  --template-file infra/main.bicep \
  --parameters environmentName="$ENVIRONMENT_NAME" location="$LOCATION" resourceGroupName="$RESOURCE_GROUP_NAME" anthropicApiKey="${ANTHROPIC_API_KEY:-}"

ACR_LOGIN_SERVER=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.containerRegistryLoginServer.value" -o tsv)

echo "3/4 - Build e push da imagem Docker para $ACR_LOGIN_SERVER..."
az acr login --name "${ACR_LOGIN_SERVER%%.*}"
docker build -t "$ACR_LOGIN_SERVER/medroutes:latest" .
docker push "$ACR_LOGIN_SERVER/medroutes:latest"

echo "4/4 - Atualizando o Container App com a nova imagem..."
CONTAINER_APP_NAME="ca-${ENVIRONMENT_NAME}"
az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP_NAME" \
  --image "$ACR_LOGIN_SERVER/medroutes:latest"

CONTAINER_APP_URL=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.containerAppUrl.value" -o tsv)
echo ""
echo "Deploy concluido!"
echo "URL da aplicacao: $CONTAINER_APP_URL"
echo "Resource Group no portal: https://portal.azure.com/#@/resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP_NAME/overview"

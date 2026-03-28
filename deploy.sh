#!/usr/bin/env bash
# deploy.sh — publica a branch atual no VPS via SSH
# Uso: ./deploy.sh [usuario@host] [diretorio-remoto]

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

VPS="${1:-openclaw@187.77.226.47}"
REMOTE_DIR="${2:-~/work-dev/dataflow-agent}"
PATCH_FILE="/tmp/dataflow-deploy-$(date +%s).patch"

# ── Cores ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[deploy]${NC} $*"; }
success() { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()    { echo -e "${YELLOW}[deploy]${NC} $*"; }
error()   { echo -e "${RED}[deploy]${NC} $*" >&2; }

# ── Pré-requisitos ─────────────────────────────────────────────────────
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  error "Não está dentro de um repositório git."
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
BASE="$(git merge-base main "$BRANCH")"
COMMITS="$(git rev-list "$BASE".."$BRANCH" --count)"

if [ "$COMMITS" -eq 0 ]; then
  error "Branch '$BRANCH' não tem commits além do main. Nada para publicar."
  exit 1
fi

if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$VPS" true &>/dev/null; then
  error "Não foi possível conectar a $VPS via SSH."
  exit 1
fi

# ── Gera patch ─────────────────────────────────────────────────────────
info "Branch: ${BOLD}$BRANCH${NC} ($COMMITS commit(s) além do main)"
info "Gerando patch..."
git format-patch main.."$BRANCH" --stdout > "$PATCH_FILE"

# ── Envia patch ────────────────────────────────────────────────────────
info "Enviando para $VPS..."
scp -q "$PATCH_FILE" "$VPS:/tmp/dataflow-deploy.patch"
rm -f "$PATCH_FILE"

# ── Aplica no VPS ──────────────────────────────────────────────────────
info "Aplicando no VPS ($REMOTE_DIR)..."
ssh "$VPS" bash <<EOF
  set -e
  cd $REMOTE_DIR

  # recria a branch com os commits do patch
  git checkout main
  git branch -D "$BRANCH" 2>/dev/null || true
  git checkout -b "$BRANCH"
  git am --abort 2>/dev/null || true
  git am /tmp/dataflow-deploy.patch
  rm -f /tmp/dataflow-deploy.patch

  echo "branch ok"
EOF

# ── Build e restart ────────────────────────────────────────────────────
info "Fazendo build e subindo containers..."
ssh "$VPS" bash <<EOF
  set -e
  cd $REMOTE_DIR
  docker compose build --quiet
  docker compose up -d
EOF

# ── Status final ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
ssh "$VPS" "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep dataflow_stack" 2>/dev/null \
  | while IFS= read -r line; do echo -e "  $line"; done
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
success "Deploy concluído → $VPS:$REMOTE_DIR (branch: $BRANCH)"

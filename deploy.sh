#!/usr/bin/env bash
# deploy.sh — cria branch, push, PR no GitHub e publica no VPS via SSH
# Uso: ./deploy.sh [usuario@host] [diretorio-remoto]
#
# Pré-requisitos:
#   gh auth login          (primeira vez)
#   gh auth setup-git      (configura credencial git via gh)

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

VPS="${1:-openclaw@187.77.226.47}"
REMOTE_DIR="${2:-~/work-dev/dataflow-agent}"
PATCH_FILE="/tmp/$(basename "$ROOT")-deploy-$(date +%s).patch"

# ── Branch base (main ou master) ───────────────────────────────────────
BASE_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')"
if [ -z "$BASE_BRANCH" ]; then
  if git show-ref --verify --quiet refs/heads/main; then
    BASE_BRANCH="main"
  elif git show-ref --verify --quiet refs/heads/master; then
    BASE_BRANCH="master"
  else
    BASE_BRANCH="main"
  fi
fi

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

if ! command -v gh &>/dev/null; then
  error "gh CLI não encontrado. Instale com: sudo pacman -S github-cli"
  error "Depois autentique: gh auth login && gh auth setup-git"
  exit 1
fi

if ! gh auth status &>/dev/null; then
  error "gh não autenticado. Rode: gh auth login"
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
BASE="$(git merge-base "$BASE_BRANCH" "$BRANCH")"
COMMITS="$(git rev-list "$BASE".."$BRANCH" --count)"

if [ "$BRANCH" = "$BASE_BRANCH" ]; then
  error "Você está na $BASE_BRANCH. Crie uma branch antes de fazer deploy."
  exit 1
fi

if [ "$COMMITS" -eq 0 ]; then
  error "Branch '$BRANCH' não tem commits além do main. Nada para publicar."
  exit 1
fi

if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$VPS" true &>/dev/null; then
  error "Não foi possível conectar a $VPS via SSH."
  exit 1
fi

# ── Push para o GitHub ─────────────────────────────────────────────────
info "Branch: ${BOLD}$BRANCH${NC} ($COMMITS commit(s) além do main)"
info "Publicando branch no GitHub..."
git push origin "$BRANCH" --force-with-lease

# ── Cria ou atualiza PR ────────────────────────────────────────────────
info "Verificando PR no GitHub..."
PR_URL="$(gh pr view "$BRANCH" --json url -q .url 2>/dev/null || true)"

if [ -z "$PR_URL" ]; then
  info "Criando Pull Request..."
  TITLE="$(git log "$BASE".."$BRANCH" --oneline | tail -1 | sed 's/^[a-f0-9]* //')"
  PR_URL="$(gh pr create \
    --base "$BASE_BRANCH" \
    --head "$BRANCH" \
    --title "$TITLE" \
    --body "$(git log "$BASE".."$BRANCH" --oneline | sed 's/^/- /')")"
  success "PR criado: $PR_URL"
else
  success "PR já existe: $PR_URL"
fi

# ── Gera e envia patch para o VPS ──────────────────────────────────────
info "Gerando patch para o VPS..."
git format-patch "$BASE_BRANCH".."$BRANCH" --stdout > "$PATCH_FILE"
scp -q "$PATCH_FILE" "$VPS:/tmp/dataflow-deploy.patch"
rm -f "$PATCH_FILE"

# ── Aplica no VPS ──────────────────────────────────────────────────────
info "Aplicando no VPS ($REMOTE_DIR)..."
ssh "$VPS" bash <<EOF
  set -e
  cd $REMOTE_DIR
  git checkout $BASE_BRANCH
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
[ -n "$PR_URL" ] && success "PR: $PR_URL"

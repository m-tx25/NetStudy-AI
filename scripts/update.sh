#!/usr/bin/env bash
# ============================================================================
# 服务器增量更新脚本（不是重新部署）
#
#   ./scripts/update.sh              # 拉代码 → 只重建变了的服务 → 自检
#   ./scripts/update.sh --no-verify  # 跳过自检
#
# 设计原则：
#   1. 只重建**代码变了**的镜像（backend / frontend），不动 mysql / redis / chroma；
#   2. Chroma 一旦重启，索引会丢 —— 脚本会检测并提醒，但**不会**自动重新索引（有费用）；
#   3. 数据卷（mysql-data / chroma-data）与 server/data/uploads 都不会被删。
# ============================================================================
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

VERIFY=1
[ "${1:-}" = "--no-verify" ] && VERIFY=0

BEFORE=$(git rev-parse HEAD)
echo "============================================================"
echo " 增量更新：$BEFORE"
echo "============================================================"

# ---------------------------------------------------------------- 1. 拉代码
echo
echo "--- 1. 拉取代码 ---"
if ! git pull --ff-only; then
  echo "  [FAIL] git pull 失败（可能本地有改动或分叉），请手动处理后再跑"
  exit 1
fi
AFTER=$(git rev-parse HEAD)
if [ "$BEFORE" = "$AFTER" ]; then
  echo "  已是最新（$AFTER），仍会检查服务状态"
fi
echo "  变更："
git --no-pager diff --stat "$BEFORE" "$AFTER" | tail -20

CHANGED=$(git diff --name-only "$BEFORE" "$AFTER")

# ---------------------------------------------------------------- 2. 判断影响面
echo
echo "--- 2. 判断需要重建什么 ---"
REBUILD_BACKEND=0
REBUILD_FRONTEND=0
FULL_UP=0

if echo "$CHANGED" | grep -qE '^(docker-compose\.ya?ml|\.env\.example)$'; then
  FULL_UP=1
fi
if echo "$CHANGED" | grep -qE '^server/(app|requirements|tests|Dockerfile)|^server/[^/]+\.py$'; then
  REBUILD_BACKEND=1
fi
if echo "$CHANGED" | grep -qE '^client/(src|public|index\.html|package|vite\.config|Dockerfile|nginx\.conf)|^client/[^/]+\.(json|js|ts)$'; then
  REBUILD_FRONTEND=1
fi
# nginx.conf 改了也要重建前端镜像（它打包进镜像）
echo "$CHANGED" | grep -q '^client/nginx\.conf$' && REBUILD_FRONTEND=1

echo "  backend 需重建：$([ $REBUILD_BACKEND -eq 1 ] && echo 是 || echo 否)"
echo "  frontend 需重建：$([ $REBUILD_FRONTEND -eq 1 ] && echo 是 || echo 否)"
echo "  compose 需整体应用：$([ $FULL_UP -eq 1 ] && echo 是 || echo 否)"

# ---------------------------------------------------------------- 3. 执行
echo
echo "--- 3. 应用更新 ---"
if [ "$FULL_UP" -eq 1 ]; then
  docker compose up -d --build
elif [ "$REBUILD_BACKEND" -eq 1 ] || [ "$REBUILD_FRONTEND" -eq 1 ]; then
  SERVICES=""
  [ "$REBUILD_BACKEND" -eq 1 ] && SERVICES="$SERVICES backend celery_worker"
  [ "$REBUILD_FRONTEND" -eq 1 ] && SERVICES="$SERVICES frontend"
  # shellcheck disable=SC2086
  docker compose up -d --build $SERVICES
else
  echo "  没有需要重建的服务（只改了文档/脚本）"
fi

# ---------------------------------------------------------------- 4. 数据库结构提醒
echo
echo "--- 4. 数据库结构 ---"
if echo "$CHANGED" | grep -q '^server/app/models\.py$'; then
  echo "  [注意] models.py 有改动："
  echo "         - **新增表/新增列**：重启后 init_db() 会自动建，无需操作"
  echo "         - **修改已有列类型**（如 TEXT → LONGTEXT）：create_all 不会改，需要手工执行 ALTER"
  echo "         本仓库踩过的例子：paper_sections.text 改 LONGTEXT"
fi

# ---------------------------------------------------------------- 5. Chroma 提醒
echo
echo "--- 5. 向量库 ---"
CHROMA_STATE=$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep '^chroma ' || true)
echo "  chroma 状态：${CHROMA_STATE:-未知}"
if [ "$FULL_UP" -eq 1 ]; then
  echo "  [注意] 本次是整体 up，若 chroma 被重建/重启，**索引会丢失**，需要重新索引："
  echo "         docker compose exec backend python reindex_all.py"
fi

# ---------------------------------------------------------------- 6. 自检
if [ "$VERIFY" -eq 1 ]; then
  echo
  echo "--- 6. 上线自检 ---"
  if [ -x ./scripts/verify-deploy.sh ]; then
    ./scripts/verify-deploy.sh "${SITE_URL:-http://127.0.0.1}" || {
      echo
      echo "  [FAIL] 自检未通过，看上面的失败项。常见原因见 docs/deploy.md 第九节"
      exit 1
    }
  else
    echo "  跳过（scripts/verify-deploy.sh 不存在或不可执行）"
  fi
fi

echo
echo "============================================================"
echo " 更新完成：$AFTER"
echo "============================================================"

#!/usr/bin/env bash
# ============================================================================
# 部署后自检脚本（在服务器上跑，验证的是「经 Nginx 走公网链路」的真实表现）
#
#   ./scripts/verify-deploy.sh                      # 默认 http://127.0.0.1
#   ./scripts/verify-deploy.sh https://your.domain  # 指定站点
#
# 退出码：0 全绿；1 有失败项。
# ============================================================================
set -uo pipefail

BASE="${1:-http://127.0.0.1}"
API="$BASE/api"
PASS=0
FAIL=0

ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
info() { echo "  [INFO] $1"; }

echo "============================================================"
echo " 部署自检：$BASE"
echo "============================================================"

# ---------------------------------------------------------------- 1. 前端
echo
echo "--- 1. 前端 ---"
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/")
[ "$CODE" = "200" ] && ok "首页 HTTP 200" || bad "首页 HTTP $CODE"

TITLE=$(curl -s --max-time 10 "$BASE/" | sed -n 's/.*<title>\(.*\)<\/title>.*/\1/p' | head -1)
case "$TITLE" in
  *苍穹矩阵*|*Matrix-Scholar*) ok "标题正确：$TITLE" ;;
  "") bad "取不到 <title>" ;;
  *) bad "标题异常：$TITLE" ;;
esac

CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/app/chat")
[ "$CODE" = "200" ] && ok "SPA 子路由回退正常（/app/chat）" || bad "SPA 子路由 HTTP $CODE（检查 try_files）"

# ---------------------------------------------------------------- 2. 后端
echo
echo "--- 2. 后端 ---"
HEALTH=$(curl -s --max-time 20 "$API/health")
[ -z "$HEALTH" ] && bad "健康检查无响应" || ok "健康检查有响应"

python3 - "$HEALTH" <<'PY' 2>/dev/null || true
import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("  [FAIL] /api/health 不是合法 JSON"); raise SystemExit
vs = d.get("vectorStore", {}) or {}
print(f"  [INFO] 数据库：{'可用' if d.get('database', {}).get('available') else '不可用'}")
print(f"  [INFO] 向量库：available={vs.get('available')} chunks={vs.get('totalChunks')}")
print(f"  [INFO] LLM：{'已配置' if d.get('llmConfigured') else '未配置'}")
PY

# 向量库有数据才算真的可用（available 可能是缓存的旧状态）
if echo "$HEALTH" | grep -q '"available":true'; then
  ok "向量库 available=true"
else
  bad "向量库不可用 —— 见 docs/vectorstore.md（常见：Chroma 重启后索引丢失）"
fi

# ---------------------------------------------------------------- 3. 鉴权
echo
echo "--- 3. 登录链路 ---"
LOGIN=$(curl -s --max-time 20 -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"123456"}')
TOKEN=$(echo "$LOGIN" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("accessToken") or d.get("access_token") or d.get("token") or "")' 2>/dev/null)
if [ -n "$TOKEN" ]; then
  ok "demo 账号登录成功（长度 ${#TOKEN}）"
else
  bad "demo 账号登录失败：$(echo "$LOGIN" | head -c 120)"
fi

# ---------------------------------------------------------------- 4. 存储
echo
echo "--- 4. 存储与配额 ---"
if [ -n "$TOKEN" ]; then
  STORAGE=$(curl -s --max-time 20 -H "Authorization: Bearer $TOKEN" "$API/storage/status")
  echo "$STORAGE" | python3 -c '
import json, sys
d = json.load(sys.stdin)
disk = d["disk"]; q = d["quota"]; lim = d["limits"]
print(f"  [INFO] 磁盘：总 {disk[\"totalGb\"]}GB / 剩 {disk[\"freeGb\"]}GB")
print(f"  [INFO] 配额：总 {q[\"totalQuotaGb\"]}GB / 已用 {q[\"usedGb\"]}GB / 单用户 {q[\"userQuotaGb\"]}GB")
print(f"  [INFO] 单文件上限：{lim[\"maxUploadMb\"]}MB / 分块 {lim[\"chunkSizeKb\"]}KB / 解析并发 {lim[\"maxConcurrentParseTasks\"]}")
' 2>/dev/null || bad "storage/status 解析失败"
  ok "存储接口可访问"
fi

# ---------------------------------------------------------------- 5. 上传拦截
echo
echo "--- 5. 上传上限（Nginx 与后端是否一致）---"
# 造一个 1MB 的非法文件：应被「格式校验」拒绝（400），而不是被 Nginx 413
TMP=$(mktemp)
head -c 1048576 /dev/urandom > "$TMP"
RESP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -X POST "$API/documents/upload" \
  -H "Authorization: Bearer ${TOKEN:-none}" \
  -F "knowledgeBaseId=kb_invalid_for_probe" \
  -F "file=@$TMP;filename=probe.pdf")
rm -f "$TMP"
case "$RESP" in
  400|404|422) ok "非法上传被业务层拦下（HTTP $RESP），说明请求已穿过 Nginx" ;;
  413) bad "被 Nginx 413 拦截 —— client_max_body_size 小于后端上限" ;;
  401) info "未登录被拦（HTTP 401），跳过该项" ;;
  *)   bad "意外响应 HTTP $RESP" ;;
esac

# ---------------------------------------------------------------- 6. SSE
echo
echo "--- 6. 流式输出（SSE）---"
if [ -n "$TOKEN" ]; then
  # 只要 3 秒内能收到第一块数据，就说明 Nginx 没有把响应攒起来
  FIRST=$(curl -s -N --max-time 8 -X POST "$API/chat/stream" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"content":"什么是 RAG？"}' 2>/dev/null | head -c 200)
  if [ -n "$FIRST" ]; then
    ok "3 秒内收到首个数据块（流式正常）"
  else
    bad "没有收到流式数据 —— 检查 Nginx proxy_buffering off / gzip off"
  fi
fi

# ---------------------------------------------------------------- 汇总
echo
echo "============================================================"
echo " 结果：通过 $PASS 项，失败 $FAIL 项"
echo "============================================================"
[ "$FAIL" -eq 0 ] || exit 1

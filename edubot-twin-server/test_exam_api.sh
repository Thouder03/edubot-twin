#!/usr/bin/env bash
# Sprint 11 考试域 API 全链路测试
set -u

BASE="http://localhost:8000/api/v1/teachers"
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"teacher","password":"teacher"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

AUTH="Authorization: Bearer $TOKEN"
CT="Content-Type: application/json"

# 唯一后缀，确保每次运行不冲突
SUFFIX=$(date +%s)
EXAM_CODE="test_${SUFFIX}"

passed=0
failed=0

assert_code() {
  local label="$1" expected="$2" actual="$3" body="$4"
  if [ "$actual" == "$expected" ]; then
    echo "  ✅ $label (HTTP $actual)"
    ((passed++))
  else
    echo "  ❌ $label — expected HTTP $expected, got $actual"
    echo "     Body: $(echo "$body" | head -c 200)"
    ((failed++))
  fi
}

api() {
  local method="$1" url="$2" data="${3:-}"
  local code
  if [ -n "$data" ]; then
    code=$(curl -so /tmp/api_resp -w '%{http_code}' -X "$method" "$url" -H "$AUTH" -H "$CT" -d "$data" 2>/dev/null) || true
  else
    code=$(curl -so /tmp/api_resp -w '%{http_code}' -X "$method" "$url" -H "$AUTH" 2>/dev/null) || true
  fi
  echo "$code"
}

echo "=============================="
echo " Sprint 11 考试域 API 测试"
echo " (exam_code=$EXAM_CODE)"
echo "=============================="

# ── 1. 考试 CRUD ─────────────────────────────────────────────────
echo -e "\n▸ 1. 考试定义 CRUD"

CODE=$(api POST "$BASE/exams" "{\"name\":\"API测试考试\",\"code\":\"$EXAM_CODE\",\"exam_mode\":\"result_run\",\"description\":\"自动化测试\"}")
BODY=$(cat /tmp/api_resp)
assert_code "创建考试" "201" "$CODE" "$BODY"
EXAM_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',0))" 2>/dev/null || echo "0")
echo "     → exam_id=$EXAM_ID"

CODE=$(api GET "$BASE/exams/$EXAM_ID")
BODY=$(cat /tmp/api_resp)
assert_code "查询考试详情" "200" "$CODE" "$BODY"

CODE=$(api GET "$BASE/exams?page=1&page_size=10")
BODY=$(cat /tmp/api_resp)
assert_code "考试列表" "200" "$CODE" "$BODY"
TOTAL=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('total','?'))" 2>/dev/null || echo "?")
echo "     → total=$TOTAL"

CODE=$(api PATCH "$BASE/exams/$EXAM_ID" '{"name":"改名后的考试","description":"已更新"}')
BODY=$(cat /tmp/api_resp)
assert_code "更新考试" "200" "$CODE" "$BODY"

CODE=$(api POST "$BASE/exams" "{\"name\":\"重复编码测试\",\"code\":\"$EXAM_CODE\",\"exam_mode\":\"process_run\"}")
BODY=$(cat /tmp/api_resp)
assert_code "重复编码 → 409" "409" "$CODE" "$BODY"

# ── 2. 环境快照 CRUD ─────────────────────────────────────────────
echo -e "\n▸ 2. 考试环境快照 CRUD"

CODE=$(api POST "$BASE/exam-env-snapshots" "{\"name\":\"env_snap_$SUFFIX\",\"container_target_dir\":\"/home/ubuntu20/test_ws\"}")
BODY=$(cat /tmp/api_resp)
assert_code "创建环境快照" "201" "$CODE" "$BODY"
ENV_SNAP_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',0))" 2>/dev/null || echo "0")
echo "     → env_snap_id=$ENV_SNAP_ID"

CODE=$(api GET "$BASE/exam-env-snapshots/$ENV_SNAP_ID")
BODY=$(cat /tmp/api_resp)
assert_code "查环境快照详情" "200" "$CODE" "$BODY"

CODE=$(api GET "$BASE/exam-env-snapshots?page=1&page_size=10")
BODY=$(cat /tmp/api_resp)
assert_code "环境快照列表" "200" "$CODE" "$BODY"

CODE=$(api PATCH "$BASE/exam-env-snapshots/$ENV_SNAP_ID" '{"name":"更名快照"}')
BODY=$(cat /tmp/api_resp)
assert_code "更新环境快照" "200" "$CODE" "$BODY"

CODE=$(api GET "$BASE/exam-env-snapshots/$ENV_SNAP_ID/files")
BODY=$(cat /tmp/api_resp)
assert_code "环境快照文件列表" "200" "$CODE" "$BODY"

# ── 3. 文件快照 CRUD ─────────────────────────────────────────────
echo -e "\n▸ 3. 考试文件快照 CRUD"

CODE=$(api POST "$BASE/exam-file-snapshots" "{\"name\":\"file_snap_$SUFFIX\"}")
BODY=$(cat /tmp/api_resp)
assert_code "创建文件快照" "201" "$CODE" "$BODY"
FILE_SNAP_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',0))" 2>/dev/null || echo "0")
echo "     → file_snap_id=$FILE_SNAP_ID"

CODE=$(api GET "$BASE/exam-file-snapshots/$FILE_SNAP_ID")
BODY=$(cat /tmp/api_resp)
assert_code "查文件快照详情" "200" "$CODE" "$BODY"

CODE=$(api GET "$BASE/exam-file-snapshots?page=1&page_size=10")
BODY=$(cat /tmp/api_resp)
assert_code "文件快照列表" "200" "$CODE" "$BODY"

CODE=$(api GET "$BASE/exam-file-snapshots/$FILE_SNAP_ID/files")
BODY=$(cat /tmp/api_resp)
assert_code "文件快照文件列表" "200" "$CODE" "$BODY"

# ── 4. 测评脚本 CRUD ─────────────────────────────────────────────
echo -e "\n▸ 4. 测评脚本包 CRUD"

CODE=$(api POST "$BASE/exam-eval-scripts" "{\"name\":\"script_$SUFFIX\",\"entry_point\":\"evaluate.sh\",\"description\":\"自动打分\"}")
BODY=$(cat /tmp/api_resp)
assert_code "创建脚本包" "201" "$CODE" "$BODY"
SCRIPT_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',0))" 2>/dev/null || echo "0")
echo "     → script_id=$SCRIPT_ID"

CODE=$(api GET "$BASE/exam-eval-scripts/$SCRIPT_ID")
BODY=$(cat /tmp/api_resp)
assert_code "查脚本包详情" "200" "$CODE" "$BODY"
VSTATUS=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('validate_status','?'))" 2>/dev/null || echo "?")
echo "     → validate_status=$VSTATUS (预期 pending)"

CODE=$(api PATCH "$BASE/exam-eval-scripts/$SCRIPT_ID" '{"name":"改名脚本"}')
BODY=$(cat /tmp/api_resp)
assert_code "更新脚本包" "200" "$CODE" "$BODY"

CODE=$(api GET "$BASE/exam-eval-scripts/$SCRIPT_ID/files")
BODY=$(cat /tmp/api_resp)
assert_code "脚本包文件列表" "200" "$CODE" "$BODY"

# ── 5. 考试资源关联 + 发布 ────────────────────────────────────────
echo -e "\n▸ 5. 考试发布流程"

CODE=$(api PATCH "$BASE/exams/$EXAM_ID" "{\"env_snapshot_id\":$ENV_SNAP_ID,\"file_snapshot_id\":$FILE_SNAP_ID,\"eval_script_id\":$SCRIPT_ID}")
BODY=$(cat /tmp/api_resp)
assert_code "关联资源到考试" "200" "$CODE" "$BODY"

CODE=$(api POST "$BASE/exams/$EXAM_ID/publish")
BODY=$(cat /tmp/api_resp)
assert_code "发布考试" "200" "$CODE" "$BODY"
STATUS=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('status','?'))" 2>/dev/null || echo "?")
echo "     → status=$STATUS (预期 published)"

# 冻结字段测试
CODE=$(api PATCH "$BASE/exams/$EXAM_ID" '{"exam_mode":"process_run"}')
BODY=$(cat /tmp/api_resp)
assert_code "冻结字段修改 → 409" "409" "$CODE" "$BODY"

# 非冻结字段仍可修改
CODE=$(api PATCH "$BASE/exams/$EXAM_ID" '{"description":"发布后仍可改描述"}')
BODY=$(cat /tmp/api_resp)
assert_code "发布后改描述 → 200" "200" "$CODE" "$BODY"

# ── 6. 归档 + 重新发布 ───────────────────────────────────────────
echo -e "\n▸ 6. 归档 → 重新发布"

CODE=$(api POST "$BASE/exams/$EXAM_ID/archive")
BODY=$(cat /tmp/api_resp)
assert_code "归档考试" "200" "$CODE" "$BODY"
STATUS=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('status','?'))" 2>/dev/null || echo "?")
echo "     → status=$STATUS (预期 archived)"

CODE=$(api POST "$BASE/exams/$EXAM_ID/republish")
BODY=$(cat /tmp/api_resp)
assert_code "重新发布" "200" "$CODE" "$BODY"
STATUS=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('status','?'))" 2>/dev/null || echo "?")
echo "     → status=$STATUS (预期 published)"

# ── 7. 引用保护 ──────────────────────────────────────────────────
echo -e "\n▸ 7. 引用保护测试（考试 published → 资源不可删）"

CODE=$(api DELETE "$BASE/exam-env-snapshots/$ENV_SNAP_ID")
BODY=$(cat /tmp/api_resp)
assert_code "删除被引用环境快照 → 409" "409" "$CODE" "$BODY"

CODE=$(api DELETE "$BASE/exam-eval-scripts/$SCRIPT_ID")
BODY=$(cat /tmp/api_resp)
assert_code "删除被引用脚本 → 409" "409" "$CODE" "$BODY"

CODE=$(api DELETE "$BASE/exam-file-snapshots/$FILE_SNAP_ID")
BODY=$(cat /tmp/api_resp)
assert_code "删除被引用文件快照 → 409" "409" "$CODE" "$BODY"

# ── 8. 清理 ──────────────────────────────────────────────────────
echo -e "\n▸ 8. 清理测试数据"

# 先归档
api POST "$BASE/exams/$EXAM_ID/archive" > /dev/null 2>&1

CODE=$(api DELETE "$BASE/exams/$EXAM_ID")
BODY=$(cat /tmp/api_resp)
assert_code "删除考试(archived)" "200" "$CODE" "$BODY"

# 考试删除后资源不再被引用
CODE=$(api DELETE "$BASE/exam-env-snapshots/$ENV_SNAP_ID")
BODY=$(cat /tmp/api_resp)
assert_code "删除环境快照" "200" "$CODE" "$BODY"

CODE=$(api DELETE "$BASE/exam-file-snapshots/$FILE_SNAP_ID")
BODY=$(cat /tmp/api_resp)
assert_code "删除文件快照" "200" "$CODE" "$BODY"

CODE=$(api DELETE "$BASE/exam-eval-scripts/$SCRIPT_ID")
BODY=$(cat /tmp/api_resp)
assert_code "删除脚本包" "200" "$CODE" "$BODY"

# ── 结果 ──────────────────────────────────────────────────────────
echo -e "\n=============================="
echo " 结果: ✅ $passed 通过, ❌ $failed 失败"
echo "=============================="

[ "$failed" -eq 0 ] && exit 0 || exit 1

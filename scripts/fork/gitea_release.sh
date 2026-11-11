#!/usr/bin/env bash
# Gitea Release 助手（fork 自用，给 .gitea/workflows/fork-release.yml 用）。
#   gitea_release.sh ensure <tag> <title> <prerelease:true|false> <notes-file>   没有就建，有就保留原说明
#   gitea_release.sh upload <tag> <file>...                                      上传附件，同名先删再传
# 环境变量：GITEA_URL（形如 https://host:port）、GITEA_REPO（owner/name）、GITEA_TOKEN。
set -euo pipefail

: "${GITEA_URL:?}" "${GITEA_REPO:?}" "${GITEA_TOKEN:?}"
API="${GITEA_URL%/}/api/v1/repos/${GITEA_REPO}"
AUTH=(-H "Authorization: token ${GITEA_TOKEN}")
# 自签证书或内网地址时可设 GITEA_CURL_OPTS=-k
read -r -a EXTRA <<<"${GITEA_CURL_OPTS:-}"

api() { curl -sS --retry 3 --retry-delay 5 "${EXTRA[@]}" "${AUTH[@]}" "$@"; }

release_json() { api -o - -w '\n%{http_code}' "${API}/releases/tags/$1"; }

cmd="${1:-}"
shift || true
case "$cmd" in
  ensure)
    tag="$1" title="$2" pre="$3" notes="$4"
    out="$(release_json "$tag")"
    if [ "${out##*$'\n'}" = 200 ]; then
      echo "Release $tag 已存在，保留原说明"
      exit 0
    fi
    body="$(python3 - "$tag" "$title" "$pre" "$notes" <<'PY'
import json, sys
tag, title, pre, notes = sys.argv[1:5]
print(json.dumps({"tag_name": tag, "name": title, "prerelease": pre == "true",
                  "body": open(notes, encoding="utf-8").read()}))
PY
)"
    code="$(api -o /tmp/gitea_rel.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d "$body" "${API}/releases")"
    # 另一个 job 同时建好了（409/422）也算成功。
    if [ "$code" != 201 ]; then
      out="$(release_json "$tag")"
      if [ "${out##*$'\n'}" != 200 ]; then
        echo "创建 Release 失败（HTTP $code）：$(cat /tmp/gitea_rel.json)" >&2
        exit 1
      fi
    fi
    echo "Release $tag 就绪"
    ;;
  upload)
    tag="$1"
    shift
    out="$(release_json "$tag")"
    [ "${out##*$'\n'}" = 200 ] || { echo "Release $tag 不存在" >&2; exit 1; }
    rid="$(printf '%s' "${out%$'\n'*}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')"
    for f in "$@"; do
      name="$(basename "$f")"
      existing="$(api "${API}/releases/${rid}/assets" | python3 -c '
import json, sys
name = sys.argv[1]
for a in json.load(sys.stdin):
    if a["name"] == name:
        print(a["id"])
' "$name")"
      for aid in $existing; do
        api -X DELETE "${API}/releases/${rid}/assets/${aid}" >/dev/null
      done
      code="$(api -o /tmp/gitea_asset.json -w '%{http_code}' -X POST \
        -F "attachment=@${f}" "${API}/releases/${rid}/assets?name=${name}")"
      if [ "$code" != 201 ]; then
        echo "上传 ${name} 失败（HTTP $code）：$(head -c 300 /tmp/gitea_asset.json)" >&2
        exit 1
      fi
      echo "已上传 ${name} ($(du -h "$f" | cut -f1))"
    done
    ;;
  *)
    echo "用法：$0 ensure <tag> <title> <prerelease> <notes-file> | upload <tag> <file>..." >&2
    exit 2
    ;;
esac

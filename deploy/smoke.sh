#!/usr/bin/env bash
# Smoke test a deployment: bash deploy/smoke.sh https://pakka.example.in
set -euo pipefail
base="${1:?usage: deploy/smoke.sh https://your-domain}"
pass=0; fail=0
check() {
  local name="$1" url="$2" expect="$3"
  if body=$(curl -fsS --max-time 15 "$url") && printf '%s' "$body" | grep -q "$expect"; then
    echo "ok   $name"; pass=$((pass + 1))
  else
    echo "FAIL $name ($url)"; fail=$((fail + 1))
  fi
}
check "web app"        "$base/"                              "Kaccha to Pakka"
check "web manifest"   "$base/manifest.webmanifest"          "Pakka"
check "api health"     "$base/api/health"                    '"status":"ok"'
check "api ready"      "$base/api/ready"                     '"status":"ready"'
check "signing key"    "$base/api/.well-known/ktp-keys.json" '"alg":"Ed25519"'
check "sandbox status" "$base/api/meta/sandbox"              '"services"'
check "consent notice" "$base/api/consents/notice?language=hi" '"lines"'
if [[ "$base" == https://* ]]; then
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "http://${base#https://}/" || true)
  if [[ "$code" =~ ^30[178]$ ]]; then
    echo "ok   http redirects to https"; pass=$((pass + 1))
  else
    echo "FAIL http to https redirect (got $code)"; fail=$((fail + 1))
  fi
fi
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]

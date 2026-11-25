#!/usr/bin/env bash
# Deploy to AWS Lightsail Containers in Mumbai (HTTPS URL included, no load balancer to set up).
# Needs: docker, AWS CLI v2 + the lightsailctl plugin, `aws configure` done.
# NOT RUN in the build sandbox (no docker or AWS there): do a dry run well before demo day.
# State is ephemeral (SQLite inside the container), which suits a demo: every deploy starts clean.
set -euo pipefail
cd "$(dirname "$0")"
SVC=${SVC:-proxy-demo}; AWS="aws --region ${AWS_REGION:-ap-south-1}"
export PROXY_SECRET=${PROXY_SECRET:-$(openssl rand -hex 24)} PROXY_APPROVER_KEY=${PROXY_APPROVER_KEY:-$(openssl rand -hex 24)} PROXY_REQUESTER_KEY=${PROXY_REQUESTER_KEY:-$(openssl rand -hex 24)}

docker build -t proxy:latest .
$AWS lightsail get-container-services --service-name "$SVC" >/dev/null 2>&1 || {
  $AWS lightsail create-container-service --service-name "$SVC" --power nano --scale 1 >/dev/null; sleep 5; }
URL=$($AWS lightsail get-container-services --service-name "$SVC" --query 'containerServices[0].url' --output text); URL=${URL%/}
REF=$($AWS lightsail push-container-image --service-name "$SVC" --label app --image proxy:latest --query 'containerImage.image' --output text)

SPEC=$(mktemp); trap 'rm -f "$SPEC"' EXIT
python3 - "$SVC" "$REF" "$URL" > "$SPEC" <<'PY'
import json, os, sys
svc, ref, url = sys.argv[1:4]
keep = ["PROXY_SECRET", "PROXY_APPROVER_KEY", "PROXY_REQUESTER_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_TTS_MODEL",
        "ELEVENLABS_VOICE_ID", "ELEVENLABS_API_BASE", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "APPROVER_WHATSAPP"]
env = {k: os.environ[k] for k in keep if os.environ.get(k)}
env["PROXY_BASE_URL"] = url
print(json.dumps({"serviceName": svc, "containers": {"app": {"image": ref, "ports": {"8000": "HTTP"}, "environment": env}},
                  "publicEndpoint": {"containerName": "app", "containerPort": 8000, "healthCheck": {"path": "/healthz"}}}))
PY
$AWS lightsail create-container-service-deployment --cli-input-json "file://$SPEC" >/dev/null
echo "Deploying to $URL (takes a few minutes). Sign-in links, shown once, keep them private:"
echo "  approver : $URL/login#approver:$PROXY_APPROVER_KEY"
echo "  requester: $URL/login#requester:$PROXY_REQUESTER_KEY"

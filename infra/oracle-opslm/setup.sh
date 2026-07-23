#!/usr/bin/env bash
# Always-on OpsLM inference on an Oracle Cloud "Always Free" ARM VM (Ubuntu).
# Installs Ollama (serves an OpenAI-compatible API), loads OpsLM from the Hub,
# and puts a token-gated Caddy proxy in front so the endpoint isn't wide open.
#
# Run once on the VM:   OPSLM_TOKEN=<pick-a-secret> bash setup.sh
# Endpoint after:       http://<vm-public-ip>:8080/v1   (bearer OPSLM_TOKEN)
set -euo pipefail

: "${OPSLM_TOKEN:?set OPSLM_TOKEN to a secret string, e.g. OPSLM_TOKEN=$(openssl rand -hex 16) bash setup.sh}"
MODEL_REF="${MODEL_REF:-hf.co/dhf1234/OpsLM-v1:Q4_K_M}"  # OpsLM GGUF on the Hub
PROXY_PORT="${PROXY_PORT:-8080}"

echo "==> 1/5 installing Ollama"
curl -fsSL https://ollama.com/install.sh | sh

echo "==> 2/5 binding Ollama to localhost + keeping the model warm"
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_KEEP_ALIVE=24h"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
sleep 5

echo "==> 3/5 loading OpsLM ($MODEL_REF) and aliasing to 'opslm'"
# Pull the GGUF straight from the Hub; alias to the short name the site requests.
ollama pull "$MODEL_REF"
ollama cp "$MODEL_REF" opslm
# Fallback if the HF tag doesn't resolve: download the GGUF and build a Modelfile
# with a ChatML template (Qwen3), then `ollama create opslm -f Modelfile`.

echo "==> 4/5 installing Caddy as a token-gated reverse proxy on :$PROXY_PORT"
sudo apt-get update -y
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
sudo apt-get update -y
sudo apt-get install -y caddy

# Caddyfile: forward only requests carrying the right bearer token to Ollama.
sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
:$PROXY_PORT {
	@authorized header Authorization "Bearer $OPSLM_TOKEN"
	handle @authorized {
		reverse_proxy 127.0.0.1:11434
	}
	respond "unauthorized" 401
}
EOF
sudo systemctl restart caddy

echo "==> 5/5 opening the VM firewall for :$PROXY_PORT"
# Oracle Ubuntu images ship a default-DROP iptables chain; allow the proxy port.
sudo iptables -I INPUT 6 -p tcp --dport "$PROXY_PORT" -j ACCEPT || true
sudo netfilter-persistent save 2>/dev/null || sudo bash -c 'iptables-save > /etc/iptables/rules.v4' 2>/dev/null || true

PUB=$(curl -s ifconfig.me || echo "<vm-public-ip>")
echo
echo "DONE. Test locally:"
echo "  curl -s http://localhost:$PROXY_PORT/v1/chat/completions -H 'Authorization: Bearer $OPSLM_TOKEN' \\"
echo "    -H 'content-type: application/json' -d '{\"model\":\"opslm\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'"
echo
echo "Wire the site (Vercel env vars), then redeploy:"
echo "  OPSLM_ENDPOINT=http://$PUB:$PROXY_PORT/v1"
echo "  OPSLM_MODEL=opslm"
echo "  OPSLM_API_KEY=$OPSLM_TOKEN"
echo
echo "!! Also open ingress TCP $PROXY_PORT in the Oracle VCN security list (see README)."

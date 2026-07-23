# Always-on OpsLM on Oracle Cloud Free Tier ($0 forever)

Hugging Face now gates Docker/Gradio Spaces behind PRO, and free micro-VMs are
too small for a 4B model. Oracle Cloud's **Always Free** ARM VM (Ampere A1: up
to 4 cores / 24 GB RAM) is the one genuinely-free, always-on option big enough
to serve OpsLM on CPU. This stands up an OpenAI-compatible, token-gated endpoint
the Vercel site calls — so the live chat stays up 24/7 without paying anything.

> **Reality check:** Oracle's free A1 capacity is in high demand; instance
> creation sometimes returns "Out of host capacity." Retry (a different
> Availability Domain, or later) — it does come through. Everything else is
> quick.

## Step 1 — Oracle account + Always Free VM (~15 min)

1. Sign up at cloud.oracle.com (needs a card for identity verification; **Always
   Free resources cost $0** and never auto-charge).
2. Console → **Compute → Instances → Create Instance**.
3. **Image & shape:** Image = **Ubuntu 22.04**; Shape → **Ampere** →
   `VM.Standard.A1.Flex` → set **4 OCPU / 24 GB** (all within Always Free).
4. **Networking:** keep "Assign a public IPv4 address" = **Yes**.
5. **SSH keys:** upload your public key (or let Oracle generate one and download
   the private key).
6. Create. Note the **public IP**.

## Step 2 — open the port in the VCN security list

Console → **Networking → Virtual Cloud Networks →** your VCN → its **public
subnet → Security List → Add Ingress Rule:**

- Source CIDR `0.0.0.0/0` · IP Protocol `TCP` · Destination Port **`8080`**

(This is Oracle's network firewall; the setup script opens the VM's own iptables
for the same port.)

## Step 3 — run the setup script

SSH in and run it with a secret token you choose:

```bash
ssh ubuntu@<public-ip>
# on the VM:
curl -fsSL https://raw.githubusercontent.com/dilipna/OPsVerse/main/infra/oracle-opslm/setup.sh -o setup.sh
OPSLM_TOKEN="$(openssl rand -hex 16)" bash setup.sh      # prints the token + endpoint at the end
```

It installs Ollama, loads OpsLM from `dhf1234/OpsLM-v1`, aliases it to `opslm`,
and fronts it with a token-gated Caddy proxy on `:8080`. **Copy the token** it
prints — you'll need it for Vercel. First model load takes a few minutes.

Test from your laptop:

```bash
curl -s http://<public-ip>:8080/v1/chat/completions \
  -H "Authorization: Bearer <token>" -H "content-type: application/json" \
  -d '{"model":"opslm","messages":[{"role":"user","content":"why is my pod CrashLooping?"}]}'
```

## Step 4 — wire the site (once)

In the Vercel project → **Settings → Environment Variables**, add:

| Var | Value |
|---|---|
| `OPSLM_ENDPOINT` | `http://<public-ip>:8080/v1` |
| `OPSLM_MODEL` | `opslm` |
| `OPSLM_API_KEY` | the token from step 3 |

**Redeploy.** The console pill flips to `● model online` and the chat answers
from the real fine-tune — permanently.

## Notes

- **Speed:** CPU inference on 4 ARM cores is a few tokens/sec — fine for a demo,
  and the model is kept warm (`OLLAMA_KEEP_ALIVE=24h`) so there's no reload lag.
- **HTTP is fine here:** the Vercel serverless proxy calls the endpoint
  server-side, so there's no browser mixed-content issue. Want HTTPS anyway? Put
  a free DuckDNS subdomain on the IP and Caddy will auto-provision a cert.
- **Point at OpsLM-v2 later:** re-run with `MODEL_REF=hf.co/dhf1234/OpsLM-v2:Q4_K_M`
  after the DPO run.
- **Security:** the token gate keeps the endpoint from being wide open. Rotate
  it by editing `/etc/caddy/Caddyfile` and `systemctl restart caddy`.

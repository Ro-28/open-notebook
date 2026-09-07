#!/bin/bash
# Configure Open Notebook to use subscription models via the local subscription-proxy:
#  - Claude (anthropic_compatible credential)  -> default for every task type (Haiku)
#  - ChatGPT/Codex (openai_compatible credential) -> selectable per task
#  - local Ollama (nomic-embed-text)            -> embeddings
set -e
API=http://localhost:5055/api
PROXY=http://127.0.0.1:3101/v1

ensure_cred_named() { # provider name json-extra  (matches by name, so several creds per provider can coexist)
  local id
  id=$(curl -s "$API/credentials/by-provider/$1" -o /tmp/c.json -w ""; python3 -c "import json;d=json.load(open('/tmp/c.json'));print(next((c['id'] for c in d if c['name']=='$2'),''))")
  if [ -z "$id" ]; then
    curl -s -X POST "$API/credentials" -H 'Content-Type: application/json' -d "{\"name\":\"$2\",\"provider\":\"$1\",$3}" -o /tmp/cred.json
    id=$(python3 -c 'import json;print(json.load(open("/tmp/cred.json"))["id"])')
  fi
  echo "$id"
}

ensure_cred() { # provider name json-extra
  local id
  id=$(curl -s "$API/credentials/by-provider/$1" -o /tmp/c.json -w ""; python3 -c 'import json;d=json.load(open("/tmp/c.json"));print(d[0]["id"] if d else "")')
  if [ -z "$id" ]; then
    curl -s -X POST "$API/credentials" -H 'Content-Type: application/json' \
      -d "{\"name\":\"$2\",\"provider\":\"$1\",$3}" -o /tmp/cred.json
    id=$(python3 -c 'import json;print(json.load(open("/tmp/cred.json"))["id"])')
  fi
  echo "$id"
}

register() { # cred provider type models...
  local cred="$1" prov="$2" type="$3"; shift 3
  local payload="["
  for m in "$@"; do payload="$payload{\"name\":\"$m\",\"provider\":\"$prov\",\"model_type\":\"$type\"},"; done
  payload="${payload%,}]"
  curl -s -X POST "$API/credentials/$cred/register-models" -H 'Content-Type: application/json' -d "{\"models\":$payload}" | head -c 200; echo
}

CLAUDE=$(ensure_cred anthropic_compatible "Claude subscription (OAuth proxy)" "\"modalities\":[\"language\"],\"api_key\":\"subscription\",\"base_url\":\"$PROXY\"")
CODEX=$(ensure_cred openai_compatible "ChatGPT subscription (OAuth proxy)" "\"modalities\":[\"language\"],\"api_key\":\"subscription\",\"base_url\":\"$PROXY\"")
OLLAMA=$(ensure_cred ollama "Ollama (local)" "\"modalities\":[\"language\",\"embedding\"],\"base_url\":\"http://localhost:11434\"")
TTS=$(ensure_cred_named openai_compatible "Edge TTS (free, via proxy)" "\"modalities\":[\"text_to_speech\"],\"api_key\":\"subscription\",\"base_url\":\"$PROXY\"")
echo "claude: $CLAUDE  codex: $CODEX  ollama: $OLLAMA"
for c in $CLAUDE $CODEX $OLLAMA; do curl -s -X POST "$API/credentials/$c/test" | head -c 160; echo; done

echo "== register"
register "$CLAUDE" anthropic_compatible language claude-haiku-4-5-20251001 claude-sonnet-5 claude-fable-5-1
register "$CODEX" openai_compatible language gpt-6-astra
register "$OLLAMA" ollama embedding nomic-embed-text
register "$TTS" openai_compatible text_to_speech edge-tts

echo "== models"
curl -s "$API/models" -o /tmp/models.json
python3 -c 'import json;[print(m["id"],m["provider"],m["type"],m["name"]) for m in json.load(open("/tmp/models.json"))]'
pick() { python3 -c "import json;print(next((m['id'] for m in json.load(open('/tmp/models.json')) if m['name']=='$1'),''))"; }
HAIKU=$(pick claude-haiku-4-5-20251001); SONNET=$(pick claude-sonnet-5); EMB=$(pick nomic-embed-text); EDGE=$(pick edge-tts)

echo "== defaults (Haiku everywhere; Sonnet for large context; nomic for embeddings; Edge TTS for speech)"
curl -s -X PUT "$API/models/defaults" -H 'Content-Type: application/json' \
  -d "{\"default_chat_model\":\"$HAIKU\",\"default_transformation_model\":\"$HAIKU\",\"large_context_model\":\"${SONNET:-$HAIKU}\",\"default_tools_model\":\"$HAIKU\",\"default_embedding_model\":\"$EMB\",\"default_text_to_speech_model\":\"$EDGE\",\"default_speech_to_text_model\":null}"; echo

echo "== podcast profiles: Haiku for outline/transcript, Edge TTS for voices (only where unset)"
curl -s "$API/episode-profiles" -o /tmp/ep.json; curl -s "$API/speaker-profiles" -o /tmp/sp.json
python3 - "$API" "$HAIKU" "$EDGE" <<'PY'
import json, sys, urllib.request
api, haiku, edge = sys.argv[1:]
def put(path, body):
    req = urllib.request.Request(f"{api}{path}", data=json.dumps(body).encode(), method="PUT", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return r.status
for e in json.load(open("/tmp/ep.json")):
    if not e.get("outline_llm") or not e.get("transcript_llm") or not e.get("max_tokens"):
        body = {k: e[k] for k in ("name","description","speaker_config","language","default_briefing","num_segments","max_tokens") if e.get(k) is not None}
        body["outline_llm"] = e.get("outline_llm") or haiku; body["transcript_llm"] = e.get("transcript_llm") or haiku
        # Esperanto's Anthropic default is max_tokens=850 — too small for a transcript segment (JSON gets cut off).
        body["max_tokens"] = e.get("max_tokens") or 8192
        print(" episode", e["name"], put(f"/episode-profiles/{e['id']}", body))
for s in json.load(open("/tmp/sp.json")):
    if not s.get("voice_model"):
        body = {"name": s["name"], "description": s.get("description"), "voice_model": edge, "speakers": s["speakers"]}
        print(" speaker", s["name"], put(f"/speaker-profiles/{s['id']}", body))
PY

echo "== model limits (context window / max output) for known models"
curl -s "$API/models" -o /tmp/models.json
python3 - "$API" <<'PY'
import json, sys, urllib.request
api = sys.argv[1]
LIMITS = {  # name prefix -> (context_window, max_tokens)
    "claude-haiku-4-5": (200_000, 8_192), "claude-sonnet-5": (1_000_000, 16_384), "claude-fable-5-1": (1_000_000, 16_384),
    "gpt-6-astra": (1_000_000, 32_768),
}
for m in json.load(open("/tmp/models.json")):
    if m["type"] != "language" or m.get("context_window"):
        continue
    for prefix, (ctx, out) in LIMITS.items():
        if m["name"].startswith(prefix):
            req = urllib.request.Request(f"{api}/models/{m['id']}", data=json.dumps({"context_window": ctx, "max_tokens": out}).encode(),
                                         method="PATCH", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                print(" ", m["name"], ctx, out, r.status)
            break
PY

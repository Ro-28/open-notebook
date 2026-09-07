#!/bin/bash
# Configure Open Notebook to use subscription models via the local subscription-proxy:
#  - Claude (anthropic_compatible credential)  -> default for every task type (Haiku)
#  - ChatGPT/Codex (openai_compatible credential) -> selectable per task
#  - local Ollama (nomic-embed-text)            -> embeddings
set -e
API=http://localhost:5055/api
PROXY=http://127.0.0.1:3101/v1

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
echo "claude: $CLAUDE  codex: $CODEX  ollama: $OLLAMA"
for c in $CLAUDE $CODEX $OLLAMA; do curl -s -X POST "$API/credentials/$c/test" | head -c 160; echo; done

echo "== register"
register "$CLAUDE" anthropic_compatible language claude-haiku-4-5-20251001 claude-sonnet-5 claude-fable-5-1
register "$CODEX" openai_compatible language gpt-5.5 gpt-5.6 gpt-6-astra
register "$OLLAMA" ollama embedding nomic-embed-text

echo "== models"
curl -s "$API/models" -o /tmp/models.json
python3 -c 'import json;[print(m["id"],m["provider"],m["type"],m["name"]) for m in json.load(open("/tmp/models.json"))]'
pick() { python3 -c "import json;print(next((m['id'] for m in json.load(open('/tmp/models.json')) if m['name']=='$1'),''))"; }
HAIKU=$(pick claude-haiku-4-5-20251001); SONNET=$(pick claude-sonnet-5); EMB=$(pick nomic-embed-text)

echo "== defaults (Haiku everywhere; Sonnet for large context; nomic for embeddings)"
curl -s -X PUT "$API/models/defaults" -H 'Content-Type: application/json' \
  -d "{\"default_chat_model\":\"$HAIKU\",\"default_transformation_model\":\"$HAIKU\",\"large_context_model\":\"${SONNET:-$HAIKU}\",\"default_tools_model\":\"$HAIKU\",\"default_embedding_model\":\"$EMB\",\"default_text_to_speech_model\":null,\"default_speech_to_text_model\":null}"; echo

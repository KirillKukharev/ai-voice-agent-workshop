#!/usr/bin/env bash
# Check AudioSocket/transport config that affects inbound audio (pre_guard_pcm_rms).
# Run from repo root: bash scripts/check-audiosocket-config.sh

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== 1. Effective audiosocket config (YAML) ==="
# Show merged audiosocket section: main + local override
python3 -c "
import yaml
import sys
with open('config/ai-agent.yaml') as f:
    main = yaml.safe_load(f) or {}
with open('config/ai-agent.local.yaml') as f:
    local = yaml.safe_load(f) or {}
# shallow merge: local overrides main for top-level keys
merged = {**main.get('audiosocket', {}), **local.get('audiosocket', {})}
print('audiosocket:')
for k, v in merged.items():
    print(f'  {k}: {v}')
fmt = merged.get('format', 'NOT SET')
if fmt == 'slin' and merged.get('format') != 'ulaw':
    print()
    print('WARNING: format is slin but Asterisk usually sends ulaw (μ-law) for telephony.')
    print('If pre_guard_pcm_rms=0, set in config/ai-agent.local.yaml:')
    print('  audiosocket:')
    print('    format: ulaw')
    print('    sample_rate: 8000')
" 2>/dev/null || {
  echo "Fallback: grep audiosocket/format from config files"
  grep -E "format:|audiosocket:" config/ai-agent.yaml config/ai-agent.local.yaml 2>/dev/null || true
}

echo ""
echo "=== 2. audio_transport ==="
grep -E "^audio_transport:|^  format:" config/ai-agent.yaml config/ai-agent.local.yaml 2>/dev/null || true

echo ""
echo "=== 3. Local provider input (expect mulaw8k for ulaw telephony) ==="
grep -E "input_mode|stream_format|mulaw" config/ai-agent.local.yaml config/ai-agent.yaml 2>/dev/null | head -20

echo ""
echo "=== 4. .env overrides (AUDIOSOCKET_FORMAT wins over YAML) ==="
grep -E "^AUDIOSOCKET_FORMAT=|^#.*AUDIOSOCKET_FORMAT" .env 2>/dev/null || true

echo ""
echo "=== 5. If pre_guard_pcm_rms stays 0 after setting format=ulaw ==="
echo "  Inbound audio from Asterisk is likely silence (RTP from phone not reaching Asterisk)."
echo "  Check:"
echo "    - AST_EXTERNAL_IP when starting Asterisk (must match softphone SIP server IP)"
echo "    - RTP ports 10000-10020 published and not blocked by firewall"
echo "  On next call, look for one-time log 'AudioSocket frame probe' with rms_pcm8k=..."
echo "  If rms_pcm8k=0 then the wire is silence."

echo ""
echo "=== 6. After changing config, restart ai_engine ==="
echo "  docker compose -p asterisk-ai-voice-agent restart ai_engine"
echo ""
echo "Then place a test call and check:"
echo "  docker compose -p asterisk-ai-voice-agent logs -f ai_engine 2>&1 | grep -E 'guard RMS|frame probe|AudioSocket inbound format'"

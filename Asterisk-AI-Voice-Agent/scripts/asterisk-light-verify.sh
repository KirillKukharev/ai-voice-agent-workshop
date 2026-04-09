#!/bin/bash
# Run inside the Asterisk container to verify SIP and dialplan.
# Usage: docker exec asterisk /bin/bash -c "apt-get update -qq && apt-get install -y -qq net-tools >/dev/null; bash -s" < scripts/asterisk-light-verify.sh
# Or copy-paste the asterisk -rx commands below after: docker exec -it asterisk rasterisk

set -e
echo "=== 1. PJSIP transports (must show transport-udp 0.0.0.0:5060) ==="
asterisk -rx "pjsip show transports" 2>/dev/null || echo "FAIL: pjsip not loaded or no transports"

echo ""
echo "=== 2. PJSIP endpoints (1001 should appear; after MicroSIP register: Contact) ==="
asterisk -rx "pjsip show endpoints" 2>/dev/null || echo "FAIL"

echo ""
echo "=== 3. Dialplan 2000@default (must show Goto from-ai-agent) ==="
asterisk -rx "dialplan show 2000@default" 2>/dev/null || echo "FAIL: no 2000 in default"

echo ""
echo "=== 4. Dialplan s@from-ai-agent (must show Stasis) ==="
asterisk -rx "dialplan show s@from-ai-agent" 2>/dev/null || echo "FAIL: no from-ai-agent context"

echo ""
echo "=== 5. Port 5060 listening (inside container) ==="
(ss -ulnp 2>/dev/null || netstat -ulnp 2>/dev/null) | grep 5060 || echo "Nothing listening on 5060 - check transport"

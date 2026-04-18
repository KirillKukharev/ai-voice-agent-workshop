#!/bin/bash

echo "🔍 Debugging Asterisk Extensions and PJSIP Configuration"
echo "========================================================"

# Check if Asterisk container is running
echo "1. Checking Asterisk container status..."
if docker ps | grep -q "wazo-docker-asterisk"; then
    echo "✅ Asterisk container is running"
else
    echo "❌ Asterisk container is not running"
    exit 1
fi

# Check dialplan
echo ""
echo "2. Checking dialplan configuration..."
docker exec wazo-docker-asterisk-1 asterisk -rx "dialplan show default"

# Check PJSIP endpoints
echo ""
echo "3. Checking PJSIP endpoints..."
docker exec wazo-docker-asterisk-1 asterisk -rx "pjsip show endpoints"

# Check PJSIP registrations
echo ""
echo "4. Checking PJSIP registrations..."
docker exec wazo-docker-asterisk-1 asterisk -rx "pjsip show registrations"

# Check ARI applications
echo ""
echo "5. Checking ARI applications..."
docker exec wazo-docker-asterisk-1 asterisk -rx "ari show applications"

# Check recent calls
echo ""
echo "6. Checking recent calls..."
docker exec wazo-docker-asterisk-1 asterisk -rx "core show calls"

# Check SIP peers
echo ""
echo "7. Checking SIP peers..."
docker exec wazo-docker-asterisk-1 asterisk -rx "sip show peers"

echo ""
echo "🎯 Testing Extensions:"
echo "- Call extension 1000 (AI Bot with ARI)"
echo "- Call extension 100 (Regular extension)"

echo ""
echo "📋 If you don't hear a ring:"
echo "1. Check if your phone is registered to Asterisk"
echo "2. Check if SIP port 5060 is accessible"
echo "3. Check if the call is reaching the container"

echo ""
echo "🔧 To reload configurations:"
echo "docker exec wazo-docker-asterisk-1 asterisk -rx 'dialplan reload'"
echo "docker exec wazo-docker-asterisk-1 asterisk -rx 'pjsip reload'"

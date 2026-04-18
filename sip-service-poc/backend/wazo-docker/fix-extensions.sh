#!/bin/bash

# Simple script to add extensions to Asterisk
docker exec wazo-docker-asterisk-1 sh -c "
cat >> /etc/asterisk/extensions.conf << 'EOF'

[default]
exten => 100,1,NoOp(Extension 100)
exten => 100,n,Set(TIMEOUT(absolute)=3600)
exten => 100,n,Set(TIMEOUT(dial)=600)
exten => 100,n,Set(TIMEOUT(ring)=600)
exten => 100,n,Set(TIMEOUT(answer)=600)
exten => 100,n,Dial(PJSIP/100,60)
exten => 100,n,Hangup()

exten => 1000,1,NoOp(AI Bot Extension 1000)
exten => 1000,n,Set(CDR(userfield)=AI Bot)
exten => 1000,n,Set(CDR(disposition)=ANSWERED)
exten => 1000,n,Set(CDR(amaflags)=DOCUMENTATION)
exten => 1000,n,Set(TIMEOUT(absolute)=3600)
exten => 1000,n,Set(TIMEOUT(dial)=600)
exten => 1000,n,Set(TIMEOUT(ring)=600)
exten => 1000,n,Set(TIMEOUT(answer)=600)
exten => 1000,n,Answer()
exten => 1000,n,Stasis(voice-bot,1000)
exten => 1000,n,Hangup()

exten => 1000,100,NoOp(Fallback)
exten => 1000,n,Set(CDR(userfield)=AI Bot Fallback)
exten => 1000,n,Set(CDR(disposition)=ANSWERED)
exten => 1000,n,Set(CDR(amaflags)=DOCUMENTATION)
exten => 1000,n,Set(TIMEOUT(absolute)=3600)
exten => 1000,n,Answer()
exten => 1000,n,Playback(tt-monkeys)
exten => 1000,n,Playback(vm-goodbye)
exten => 1000,n,Hangup()
EOF
"

echo "✅ Extensions added with timeout settings"
echo "🔄 Reloading dialplan..."
docker exec wazo-docker-asterisk-1 asterisk -rx "dialplan reload"

echo "🔄 Reloading PJSIP configuration..."
docker exec wazo-docker-asterisk-1 asterisk -rx "pjsip reload"

echo "📋 Current dialplan for extension 1000:"
docker exec wazo-docker-asterisk-1 asterisk -rx "dialplan show default"

echo "📋 PJSIP endpoint 1000 status:"
docker exec wazo-docker-asterisk-1 asterisk -rx "pjsip show endpoints" | grep 1000

echo "📋 PJSIP AOR 1000 status:"
docker exec wazo-docker-asterisk-1 asterisk -rx "pjsip show aors" | grep 1000

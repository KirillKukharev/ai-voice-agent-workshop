#!/bin/sh
# Inject external_media_address / external_signaling_address for NAT when AST_EXTERNAL_IP is set.
# This makes SDP contain an IP the phone can send RTP to (e.g. host IP when Asterisk runs in Docker).
# Fixed RTP range: 10000-10020 (set in rtp.conf). Publish: -p 5060:5060/udp -p 10000-10020:10000-10020/udp
if [ -n "${AST_EXTERNAL_IP}" ] && ! grep -q 'external_media_address' /etc/asterisk/my_pjsip.conf 2>/dev/null; then
    sed -i "/bind = 0.0.0.0/a\\
external_media_address = ${AST_EXTERNAL_IP}\\
external_signaling_address = ${AST_EXTERNAL_IP}" /etc/asterisk/my_pjsip.conf
    echo "PJSIP NAT: set external_media_address and external_signaling_address to ${AST_EXTERNAL_IP}"
else
    if [ -z "${AST_EXTERNAL_IP}" ]; then
        echo "PJSIP NAT: AST_EXTERNAL_IP not set - phone may not reach RTP. Set it to the same IP as in your softphone (e.g. 172.30.100.139), or run with: docker run --network host ..."
    fi
fi
echo "SIP: 5060/udp  RTP: 10000-10020/udp  (publish with -p 5060:5060/udp -p 10000-10020:10000-10020/udp)"
exec asterisk -f

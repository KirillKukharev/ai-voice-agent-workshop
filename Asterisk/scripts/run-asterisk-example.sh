#!/usr/bin/env bash
# Example: run from Asterisk/  after:
#   docker build --network=host -f Dockerfile-asterisk -t asterisk-light:latest .
# Set AST_EXTERNAL_IP to an address your phone can reach (host IP, not 127.0.0.1).
set -euo pipefail
AST_EXTERNAL_IP="${AST_EXTERNAL_IP:-172.30.100.139}"
exec docker run -d --name asterisk \
  -e "AST_EXTERNAL_IP=${AST_EXTERNAL_IP}" \
  -p 5060:5060/udp -p 5060:5060/tcp \
  -p 10000-10020:10000-10020/udp \
  -p 5038:5038/tcp -p 8088:8088/tcp -p 8089:8089/tcp -p 9100:9100/tcp \
  asterisk-light:latest

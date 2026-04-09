# Asterisk in Docker: No Audio (RTP Not Reaching Asterisk)

If the call connects but you hear no AI response and logs show **no** "Media RX confirmed" or "AudioSocket inbound first audio", Asterisk is not receiving RTP from the phone. The AI engine never gets inbound audio, so STT/LLM/TTS never run.

## 1. Use the same RTP port range everywhere

- The image uses **RTP ports 10000–10020** (see `Dosckerfile-asterisk` and entrypoint).
- Publish exactly that range when running the container:
  ```bash
  -p 10000-10020:10000-10020/udp
  ```
- If you use a different range (e.g. 10000–10050), either change the image to match or publish the full 10000–10050.

## 2. Set AST_EXTERNAL_IP so the phone can send RTP

When Asterisk runs in Docker, it sees its own IP as the container IP (e.g. 172.17.0.3). The SDP sent to the phone would then contain that address; the phone often cannot reach it (e.g. phone on Windows, Asterisk in WSL2 Docker).

Set **AST_EXTERNAL_IP** to the **same IP you use in the softphone as SIP server/domain** (so the SDP tells the phone to send RTP to that address):

```bash
# Must match the IP in your softphone (domain/SIP server). Examples:
# export AST_EXTERNAL_IP=172.30.100.139   # WSL2 interface (if softphone uses this)
# export AST_EXTERNAL_IP=172.30.96.1     # Windows host (if softphone uses this)
export AST_EXTERNAL_IP=172.30.100.139

docker run -d --name asterisk \
  -e AST_EXTERNAL_IP \
  -p 5060:5060/udp \
  -p 10000-10020:10000-10020/udp \
  ... \
  asterisk-light:latest
```

Then **recreate** the container (not just restart) so the entrypoint rewrites `my_pjsip.conf` with `external_media_address` / `external_signaling_address`. Check inside the container:

```bash
docker exec asterisk grep external_media_address /etc/asterisk/my_pjsip.conf
```

## 3. Alternative: run Asterisk with network_mode: host

This avoids NAT and port mapping: Asterisk binds to the host network, so the SDP will contain the host’s real IP and the phone can send RTP directly.

```bash
docker run -d --name asterisk \
  --network host \
  -e TZ=Europe/Rome \
  asterisk-light:latest
```

- No `-p` is needed; Asterisk listens on 5060 and 10000–10020 on the host.
- Ensure **ai_engine** can reach ARI (e.g. `ASTERISK_HOST=127.0.0.1` if both run on the same host).
- If the host has several IPs, Asterisk will bind to 0.0.0.0; the phone should use the same IP you use for SIP (e.g. LAN IP).

## 4. Stasis app "doesn't exist" / "Failed to find outbound websocket"

If Asterisk logs show:
- `Stasis app 'asterisk-ai-voice-agent' doesn't exist`
- `Failed to find outbound websocket per-call config for app 'asterisk-ai-voice-agent'`

the **ai_engine** is not connected to ARI when the call arrives. The Stasis app is created when ai_engine connects to the ARI WebSocket and subscribes to the app.

**Do this:**
1. Start (or restart) **Asterisk** first.
2. Start (or restart) **ai_engine** so it connects to ARI (e.g. `ASTERISK_HOST=127.0.0.1` when Asterisk port 8088 is published to the host).
3. In ai_engine logs, wait for: `Successfully connected to ARI WebSocket`.
4. Then place a call (dial 2000 or 2001).

If you recreated the Asterisk container, restart ai_engine so it opens a new WebSocket to the new Asterisk instance.

## 5. Verify

After a test call, check ai_engine logs:

- **Success:** you see "Media RX confirmed (AudioSocket)" or "AudioSocket inbound first audio", then STT/LLM/TTS activity and playback.
- **Still no audio:** you see "RCA_CALL_END" with `media_rx_confirmed=False` and no "Media RX confirmed". Then RTP from the phone is still not reaching Asterisk — re-check AST_EXTERNAL_IP, port publishing, and firewall, or switch to `network_mode: host`.
- **RTP OK but no voice reply / "Provider event for unknown call":** the AI (STT→LLM→TTS) answered **after** you hung up. With the local pipeline (Vosk + local LLM + Piper), the first response can take **10–30 seconds**. Stay on the line at least 15–20 seconds after asking a question so the reply can be played.
- **TTS sounds like noise/static:** usually a format or byte-order mismatch on the **egress** (engine → Asterisk). In Admin UI: **(1)** Config → **AudioSocket** (or Transport) → set **Format** to **μ-law (8kHz)** so Piper’s uLaw is sent as-is (no PCM conversion). **(2)** If you keep **SLIN**, try Config → **Streaming** → **Egress Swap Mode** → **Swap (force byte swap)**. Save and restart ai_engine.

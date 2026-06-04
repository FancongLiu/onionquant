"""WeChat Work callback handler — inbound messages from 企业微信 → chairman_inbox.

GET  /api/wechat/callback — URL verification (echostr)
POST /api/wechat/callback — message receiving (encrypted XML → inbox)

Encryption: AES-256-CBC per 企业微信 technical docs.
"""

import base64
import hashlib
import json
import logging
import os
import struct
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"

router = APIRouter(tags=["wechat"])

WECOM_CORP_ID = os.getenv("WECHAT_CORP_ID", "")
WECOM_CALLBACK_TOKEN = os.getenv("WECHAT_CALLBACK_TOKEN", "")
WECOM_CALLBACK_AES_KEY = os.getenv("WECHAT_CALLBACK_AES_KEY", "")


def _verify_signature(
    token: str, timestamp: str, nonce: str, encrypt: str, sig: str
) -> bool:
    """SHA1(sort([token, ts, nonce, encrypt])) == msg_signature."""
    parts = sorted([token, timestamp, nonce, encrypt])
    raw = "".join(parts)
    computed = hashlib.sha1(raw.encode()).hexdigest()
    return computed == sig


def _decrypt_msg(encrypt: str) -> bytes:
    """Decrypt a single encrypted message per 企业微信 protocol.

    AESKey = base64.b64decode(aes_key + "=")
    AES-256-CBC, IV = key[:16]
    Plaintext layout: 16 random bytes + 4 bytes network-order msg_len + msg + corp_id
    """
    aes_key_str = WECOM_CALLBACK_AES_KEY
    if not aes_key_str.endswith("="):
        aes_key_str += "="
    aes_key = base64.b64decode(aes_key_str)
    cipher = AES.new(aes_key, AES.MODE_CBC, iv=aes_key[:16])
    raw = cipher.decrypt(base64.b64decode(encrypt))

    # Strip PKCS#7 padding
    raw = unpad(raw, AES.block_size)

    # Parse layout: 16 bytes random + 4 bytes msg_len (big-endian) + msg + receiveid
    msg_len = struct.unpack(">I", raw[16:20])[0]
    msg = raw[20 : 20 + msg_len]
    receive_id = raw[20 + msg_len :].decode("utf-8")

    if receive_id != WECOM_CORP_ID:
        logger.warning(
            f"WeChat callback: receiveid mismatch, expected {WECOM_CORP_ID}, got {receive_id}"
        )

    return msg


def _parse_msg_xml(xml_bytes: bytes) -> dict:
    """Parse decrypted WeChat XML message. Returns simplified dict."""
    root = ET.fromstring(xml_bytes.decode("utf-8"))
    result = {}
    for child in root:
        result[child.tag] = child.text or ""

    msg_type = result.get("MsgType", "")
    event = result.get("Event", "")
    return {
        "from_user": result.get("FromUserName", ""),
        "to_user": result.get("ToUserName", ""),
        "msg_type": msg_type,
        "event": event,
        "content": result.get("Content", ""),
        "msg_id": result.get("MsgId", ""),
        "create_time": result.get("CreateTime", ""),
        "raw": result,
    }


@router.get("/api/wechat/callback")
async def wechat_verify(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """URL verification — 企业微信 sends GET with echostr, we decrypt and return."""
    if not all([WECOM_CALLBACK_TOKEN, WECOM_CALLBACK_AES_KEY]):
        logger.error("WeChat callback not configured (missing TOKEN/AES_KEY)")
        return Response("not configured", status_code=500)

    if not _verify_signature(
        WECOM_CALLBACK_TOKEN, timestamp, nonce, echostr, msg_signature
    ):
        logger.warning("WeChat callback: signature verification failed")
        return Response("signature failed", status_code=403)

    try:
        plaintext = _decrypt_msg(echostr)
        logger.info("WeChat callback: URL verification succeeded")
        return PlainTextResponse(plaintext.decode("utf-8"))
    except Exception as e:
        logger.error(f"WeChat callback: decryption failed: {e}")
        return Response("decrypt failed", status_code=500)


@router.post("/api/wechat/callback")
async def wechat_receive(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """Receive inbound WeChat message — decrypt, parse, write to inbox."""
    if not all([WECOM_CALLBACK_TOKEN, WECOM_CALLBACK_AES_KEY]):
        return Response("not configured", status_code=500)

    body = await request.body()
    body_str = body.decode("utf-8")

    # Extract <Encrypt> from XML
    root = ET.fromstring(body_str)
    encrypt_elem = root.find("Encrypt")
    if encrypt_elem is None or not encrypt_elem.text:
        return Response("missing Encrypt", status_code=400)

    encrypt = encrypt_elem.text

    if not _verify_signature(
        WECOM_CALLBACK_TOKEN, timestamp, nonce, encrypt, msg_signature
    ):
        return Response("signature failed", status_code=403)

    try:
        decrypted = _decrypt_msg(encrypt)
        msg = _parse_msg_xml(decrypted)

        # Write to inbox
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"WX_{ts}.json"
        filepath = INBOX_DIR / filename
        filepath.write_text(
            json.dumps(msg, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Also write a human-readable markdown version
        md_name = f"MSG_wechat_{ts}.md"
        md_path = INBOX_DIR / md_name

        from_user = msg.get("from_user", "unknown")
        content = msg.get("content", "")
        msg_type = msg.get("msg_type", "?")
        event = msg.get("event", "")

        md_content = "# 董事长微信消息\n\n"
        md_content += (
            f"**时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 北京时间\n"
        )
        md_content += f"**来源**：企业微信 (from={from_user})\n"
        md_content += f"**类型**：{msg_type}"
        if event:
            md_content += f" / {event}"
        md_content += "\n\n"
        md_content += f"**内容**：\n{content}\n"

        md_path.write_text(md_content, encoding="utf-8")

        logger.info(f"WeChat inbound: {filename} (type={msg_type}, from={from_user})")

    except Exception as e:
        logger.error(f"WeChat callback: processing failed: {e}")
        return Response("processing failed", status_code=500)

    return PlainTextResponse("success")


# ─── Alias routes for /wecom/callback (chairman-configured URL) ───


@router.get("/wecom/callback")
async def wecom_verify(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """Alias for /api/wechat/callback GET — URL verification."""
    return await wechat_verify(msg_signature, timestamp, nonce, echostr)


@router.post("/wecom/callback")
async def wecom_receive(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """Alias for /api/wechat/callback POST — message receiving."""
    return await wechat_receive(request, msg_signature, timestamp, nonce)

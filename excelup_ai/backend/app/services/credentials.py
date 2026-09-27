"""Verifiable credentials: Ed25519 signatures + Merkle tree (§7).

- Keypair generated once at seed time and persisted in the events table as a
  bootstrap record (aggregate_type: 'crypto') so restarts reuse it.
- On gauntlet approval a credential payload is signed; seeded credentials are
  batched into a Merkle tree whose roots + proofs are stored per credential.
- GET /verify/{id} (public) shows payload + signature validity + Merkle proof.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.tables import Credential, Event


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# --------------------------------------------------------------------- keys
def generate_keypair() -> tuple[str, str]:
    """Returns (public_key_b64, secret_key_b64) for a fresh Ed25519 keypair."""
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    priv = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _b64e(bytes(pub)), _b64e(bytes(priv))


def sign_message(secret_b64: str, message: bytes) -> str:
    key = Ed25519PrivateKey.from_private_bytes(_b64d(secret_b64))
    return _b64e(key.sign(message))


def verify_signature(public_b64: str, message: bytes, signature_b64: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64d(public_b64))
        pub.verify(_b64d(signature_b64), message)
        return True
    except Exception:
        return False


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


# -------------------------------------------------------------- Merkle tree
def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def _leaf(data: bytes) -> bytes:
    return _h(b"\x00" + data)


def _node(l: bytes, r: bytes) -> bytes:
    return _h(b"\x01" + l + r)


def merkle_root(leaf_payloads: list[bytes]) -> str:
    if not leaf_payloads:
        return ""
    level = [_leaf(p) for p in leaf_payloads]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [_node(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return _b64e(level[0])


def merkle_proof(leaf_payloads: list[bytes], index: int) -> list[dict]:
    """Audit path: list of {hash, side} where side is the sibling's position."""
    level = [_leaf(p) for p in leaf_payloads]
    idx = index
    proof: list[dict] = []
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        sibling_idx = idx ^ 1
        proof.append({"hash": _b64e(level[sibling_idx]),
                      "side": "left" if sibling_idx < idx else "right"})
        level = [_node(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_merkle_proof(leaf_payload: bytes, proof: list[dict], root_b64: str) -> bool:
    h = _leaf(leaf_payload)
    for step in proof:
        sib = _b64d(step["hash"])
        h = _node(sib, h) if step["side"] == "left" else _node(h, sib)
    return _b64e(h) == root_b64


# ---------------------------------------------------------- key persistence
async def get_or_create_keypair(session: AsyncSession) -> tuple[str, str]:
    """Loads the server keypair from the events audit table, creating if absent."""
    res = await session.execute(
        select(Event).where(Event.aggregate_type == "crypto",
                            Event.event_type == "server_keypair")
        .order_by(Event.ts.desc()).limit(1)
    )
    ev = res.scalar_one_or_none()
    if ev and (ev.payload or {}).get("public_key"):
        return ev.payload["public_key"], ev.payload["secret_key"]

    pub, sec = generate_keypair()
    session.add(Event(aggregate_type="crypto", aggregate_id=0,
                      event_type="server_keypair",
                      payload={"public_key": pub, "secret_key": sec,
                               "algo": "Ed25519"}))
    await session.commit()
    return pub, sec


# ------------------------------------------------------ credential lifecycle
def credential_payload(trainee_name: str, company_name: str, skill: str,
                       level: float, challenge_title: str, date: datetime) -> dict:
    return {
        "trainee": trainee_name,
        "company": company_name,
        "skill": skill,
        "level": round(level, 2),
        "challenge": challenge_title,
        "date": date.date().isoformat(),
    }


async def mint_credential(session: AsyncSession, user_id: int, artifact_id: int,
                          payload: dict) -> Credential:
    """Sign payload with the server key and persist the credential."""
    pub, sec = await get_or_create_keypair(session)
    sig = sign_message(sec, canonical(payload))
    cred = Credential(
        user_id=user_id,
        artifact_id=artifact_id,
        payload=payload,
        signature=sig,
        merkle_root="",
        status="active",
    )
    session.add(cred)
    await session.commit()
    await session.refresh(cred)
    return cred


async def batch_merkle(session: AsyncSession) -> int:
    """Batch ALL active credentials into a Merkle tree; store roots + proofs."""
    creds = (await session.execute(
        select(Credential).where(Credential.status == "active")
        .order_by(Credential.id)
    )).scalars().all()
    leaves = [canonical(c.payload) for c in creds]
    root = merkle_root(leaves)
    for i, c in enumerate(creds):
        c.merkle_root = root
        c.payload = {**c.payload, "_merkle_proof": merkle_proof(leaves, i)}
        session.add(c)
    await session.commit()
    return len(creds)


async def verify_credential(session: AsyncSession, credential_id: int) -> dict:
    """Public verification: signature + Merkle proof against the stored root."""
    cred = (await session.execute(
        select(Credential).where(Credential.id == credential_id)
    )).scalar_one_or_none()
    if cred is None:
        return {"found": False}

    pub, _sec = await get_or_create_keypair(session)
    payload = dict(cred.payload or {})
    proof = payload.pop("_merkle_proof", [])
    body = canonical(payload)
    sig_ok = verify_signature(pub, body, cred.signature)

    proof_ok: Optional[bool] = None
    if cred.merkle_root and proof:
        proof_ok = verify_merkle_proof(body, proof, cred.merkle_root)

    return {
        "found": True,
        "credential_id": cred.id,
        "payload": payload,
        "issued_at": cred.issued_at.isoformat(),
        "status": cred.status,
        "signature_valid": sig_ok,
        "merkle_root": cred.merkle_root,
        "merkle_proof_valid": proof_ok,
        "authentic": bool(sig_ok and proof_ok is not False),
    }

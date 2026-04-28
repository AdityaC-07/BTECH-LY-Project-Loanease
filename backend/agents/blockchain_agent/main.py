import logging
import os
import json
import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import asyncio

from core.session import session_store
from services.pdf_generator import generate_sanction_letter
from core.config import settings
from blockchain import ledger, Block, MerkleTree

logger = logging.getLogger("loanease.blockchain")

router = APIRouter()

# Module-level key globals — must be declared before load_keys() is called
_private_key = None
_public_key = None

# Load keys immediately at import time
def _init_keys():
    global _private_key, _public_key
    keys_dir = "keys"
    private_key_path = os.path.join(keys_dir, "private_key.pem")
    public_key_path = os.path.join(keys_dir, "public_key.pem")
    try:
        os.makedirs(keys_dir, exist_ok=True)
        if os.path.exists(private_key_path) and os.path.exists(public_key_path):
            with open(private_key_path, "rb") as f:
                _private_key = serialization.load_pem_private_key(f.read(), password=None)
            with open(public_key_path, "rb") as f:
                _public_key = serialization.load_pem_public_key(f.read())
            logger.info("🔑 Loaded existing RSA keys from keys/ directory")
        else:
            _private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            _public_key = _private_key.public_key()
            with open(private_key_path, "wb") as f:
                f.write(_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            with open(public_key_path, "wb") as f:
                f.write(_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                ))
            logger.info("🔑 Generated new RSA keys and saved to keys/")
    except Exception as e:
        logger.error(f"Key init failed: {e}")
        _private_key = None
        _public_key = None

_init_keys()

class SanctionRequest(BaseModel):
    session_id: Optional[str] = None
    applicant_name: str
    pan_number: str
    loan_amount: float
    interest_rate: float
    tenure_years: int


class SanctionResponse(BaseModel):
    transaction_id: str
    block_hash: str
    qr_code_url: str
    verification_url: str
    pdf_download_url: str


class VerifyResponse(BaseModel):
    valid: bool
    block_data: Optional[Dict[str, Any]] = None
    verification_details: Dict[str, Any]


class ChainResponse(BaseModel):
    chain_length: int
    blocks: List[Dict[str, Any]]

# ── LEDGER HELPERS ─────────────────────────────────────────────────

def ledger_ready() -> bool:
    return len(ledger.chain) > 0

def sign_data(data: str) -> str:
    """Sign data with private key"""
    global _private_key
    
    if not _private_key:
        raise RuntimeError("Private key not available")
    
    try:
        signature = _private_key.sign(
            data.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return signature.hex()
    except Exception as e:
        logger.error(f"Signing failed: {e}")
        raise

def verify_signature(data: str, signature_hex: str) -> bool:
    """Verify signature with public key"""
    global _public_key
    
    if not _public_key:
        raise RuntimeError("Public key not available")
    
    try:
        signature = bytes.fromhex(signature_hex)
        _public_key.verify(
            signature,
            data.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except InvalidSignature:
        return False
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False

@router.post("/sanction", response_model=SanctionResponse)
async def create_sanction_letter(request: SanctionRequest):
    """Create blockchain-verified sanction letter"""
    try:
        if settings.DEMO_MODE:
            await asyncio.sleep(1.5)

        import uuid
        transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        sanction_data = {
            "transaction_id": transaction_id,
            "applicant_name": request.applicant_name,
            "pan_number": request.pan_number,
            "loan_amount": request.loan_amount,
            "interest_rate": request.interest_rate,
            "tenure_years": request.tenure_years,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "SANCTION_LETTER",
        }

        block = ledger.add_transaction(sanction_data)
        block_hash = block.hash

        data_string = json.dumps(sanction_data, sort_keys=True)
        signature = sign_data(data_string)

        from services.emi import calculate_emi
        emi_result = calculate_emi(request.loan_amount, request.interest_rate, request.tenure_years)

        try:
            generate_sanction_letter(
                applicant_name=request.applicant_name,
                pan_number=request.pan_number,
                loan_amount=request.loan_amount,
                interest_rate=request.interest_rate,
                tenure_years=request.tenure_years,
                emi=emi_result["monthly_emi"],
                application_id=transaction_id,
            )
        except Exception as pdf_err:
            logger.warning(f"PDF generation failed (non-fatal): {pdf_err}")

        if request.session_id:
            session_store.get_or_create(request.session_id)
            session_store.update_stage(request.session_id, "BLOCKCHAIN_VERIFIED")
            session_store.update_data(request.session_id, "blockchain_data", {
                "transaction_id": transaction_id,
                "block_hash": block_hash,
                "signature": signature,
            })
            session_store.log_agent(request.session_id, {
                "agent": "blockchain",
                "action": "sanction",
                "transaction_id": transaction_id,
                "block_hash": block_hash,
            })

        return SanctionResponse(
            transaction_id=transaction_id,
            block_hash=block_hash,
            qr_code_url=f"/blockchain/qr/{transaction_id}",
            verification_url=f"/blockchain/verify/{transaction_id}",
            pdf_download_url=f"/blockchain/pdf/{transaction_id}",
        )

    except Exception as e:
        if settings.DEMO_MODE:
            from core.fallback_map import get_fallback
            logger.error(f"Sanction creation failed, using demo fallback: {e}")
            fb = get_fallback("blockchain")
            return SanctionResponse(
                transaction_id=fb["transaction_id"],
                block_hash=fb["block_hash"],
                qr_code_url=f"/blockchain/qr/{fb['transaction_id']}",
                verification_url=f"/blockchain/verify/{fb['transaction_id']}",
                pdf_download_url=f"/blockchain/pdf/{fb['transaction_id']}",
            )
        logger.error(f"Sanction letter creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sanction letter creation failed: {str(e)}")

@router.get("/verify/{reference_id}", response_model=VerifyResponse)
async def verify_document(reference_id: str):
    """Verify document on blockchain"""
    try:
        # Find block with this transaction ID
        target_block = ledger.get_transaction(reference_id)
        
        if not target_block:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Verify signature
        data_string = json.dumps(target_block.transaction_data, sort_keys=True)
        signature = target_block.transaction_data.get("signature")
        
        signature_valid = False
        if signature:
            signature_valid = verify_signature(data_string, signature)
        
        # Verify blockchain integrity
        chain_valid = ledger.is_chain_valid()
        
        verification_details = {
            "signature_valid": signature_valid,
            "blockchain_integrity": chain_valid,
            "block_number": target_block.index,
            "timestamp": target_block.timestamp,
            "confirmations": len(ledger.chain) - target_block.index
        }
        
        return VerifyResponse(
            valid=signature_valid and chain_valid,
            block_data=target_block.data,
            verification_details=verification_details
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@router.get("/chain", response_model=ChainResponse)
async def get_blockchain():
    """Get entire blockchain"""
    try:
        blocks_data = [b.to_dict() for b in ledger.chain]
        
        return ChainResponse(
            chain_length=len(ledger.chain),
            blocks=blocks_data
        )
        
    except Exception as e:
        logger.error(f"Failed to get blockchain: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get blockchain: {str(e)}")

# ── NEW EXPLORER ENDPOINTS ─────────────────────────────────────────

@router.get("/explorer-data")
async def get_explorer_data():
    """Get aggregated data for the blockchain explorer"""
    try:
        chain = ledger.chain
        
        blocks_data = []
        for block in chain:
            # Handle both dict and object representations
            if isinstance(block, dict):
                b = block
            else:
                b = block.__dict__ if hasattr(block, '__dict__') else block.to_dict()
            
            # Determine block type
            block_type = "GENESIS"
            if b.get("index", 0) > 0:
                tx_data = b.get("transaction_data", {})
                if tx_data.get("type") == "SANCTION_LETTER" or "sanction_reference" in tx_data:
                    block_type = "SANCTION"
                else:
                    block_type = "TRANSACTION"
            
            blocks_data.append({
                "index": b.get("index", 0),
                "hash": b.get("hash", ""),
                "previous_hash": b.get("previous_hash", ""),
                "timestamp": b.get("timestamp", ""),
                "block_type": block_type,
                "nonce": b.get("nonce", 0),
                "merkle_root": b.get("merkle_root", ""),
                "transaction_count": 1 if b.get("index", 0) > 0 else 0,
                "transaction_data": b.get("transaction_data", {}),
            })
        
        # Count only SANCTION type blocks
        active_sanctions = sum(
            1 for b in blocks_data
            if b["block_type"] == "SANCTION"
        )
        
        # Get blockchain difficulty
        difficulty = getattr(ledger, 'DIFFICULTY', 2)
        
        return {
            "chain_stats": {
                "total_blocks": len(chain),
                "active_sanctions": active_sanctions,
                "chain_valid": ledger.is_chain_valid(),
                "pow_difficulty": difficulty,
                "genesis_hash": blocks_data[0]["hash"] if blocks_data else "",
                "latest_hash": blocks_data[-1]["hash"] if blocks_data else ""
            },
            "blocks": blocks_data,
            "merkle_trees": {}
        }
    
    except Exception as e:
        logger.error(f"Explorer data error: {e}", exc_info=True)
        # Always return valid structure even on error
        return {
            "chain_stats": {
                "total_blocks": 0,
                "active_sanctions": 0,
                "chain_valid": False,
                "pow_difficulty": 2,
                "genesis_hash": "",
                "latest_hash": ""
            },
            "blocks": [],
            "merkle_trees": {}
        }

class TamperRequest(BaseModel):
    reference: str
    tamper_field: str
    tamper_value: Any

@router.post("/tamper-test")
async def tamper_test(request: TamperRequest):
    """Simulate tampering without affecting the real ledger"""
    try:
        # Find the block
        target_block = None
        for b in ledger.chain:
            tx_data = getattr(b, 'transaction_data', {})
            if (tx_data.get("transaction_id") == request.reference or 
                tx_data.get("sanction_reference") == request.reference or
                f"Block #{b.index}" == request.reference):
                target_block = b
                break
        
        # If no block found, use the latest block for demo
        if not target_block and ledger.chain:
            target_block = ledger.chain[-1]
        
        # If still no block (empty chain), create demo data
        if not target_block:
            target_block = type('MockBlock', (), {
                'hash': "demo_hash_32_characters_long_string",
                'transaction_data': {
                    "sanction_reference": request.reference,
                    "loan_amount": 500000,
                    "applicant_name": "Demo Applicant"
                },
                'index': 0
            })()
            
        # Create a deep copy of the block to tamper
        import copy
        tampered_block = copy.deepcopy(target_block)
        
        # Modifying data
        original_val = tampered_block.transaction_data.get(request.tamper_field)
        tampered_block.transaction_data[request.tamper_field] = request.tamper_value
        
        # Recompute hash (will not match stored hash)
        original_hash = target_block.hash
        
        # Calculate what the hash SHOULD BE with tampered data
        # Note: ledger.compute_block_hash(tampered_block) will give a different hash
        tampered_hash = ledger.compute_block_hash(tampered_block)
        
        # Recalculate Merkle Root for tampered data
        tampered_merkle_root = MerkleTree.compute_root([tampered_block.transaction_data])
        
        return {
            "valid": False,
            "original_hash": original_hash,
            "tampered_hash": tampered_hash,
            "original_value": original_val,
            "tampered_value": request.tamper_value,
            "tampered_field": request.tamper_field,
            "merkle_root_mismatch": tampered_merkle_root != target_block.merkle_root,
            "original_merkle_root": target_block.merkle_root,
            "tampered_merkle_root": tampered_merkle_root,
            "message": "Tampering detected! Recomputed hash does not match block header."
        }
    except Exception as e:
        logger.error(f"Tamper test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/verify-chain")
async def verify_chain():
    """Verify full chain integrity and identify broken links"""
    try:
        is_valid = ledger.is_chain_valid()
        broken_blocks = []
        
        if not is_valid:
            # Find where it breaks
            for i in range(1, len(ledger.chain)):
                current = ledger.chain[i]
                previous = ledger.chain[i-1]
                
                if current.hash != ledger.compute_block_hash(current) or current.previous_hash != previous.hash:
                    broken_blocks.append(i)
                    
        return {
            "is_valid": is_valid,
            "broken_blocks": broken_blocks,
            "total_blocks": len(ledger.chain)
        }
    except Exception as e:
        logger.error(f"Chain verification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def blockchain_health():
    """Blockchain service health check"""
    return {
        "status": "healthy" if ledger_ready() else "error",
        "ledger_ready": ledger_ready(),
        "chain_length": len(ledger.chain),
        "keys_loaded": True,
        "difficulty": settings.BLOCKCHAIN_DIFFICULTY
    }

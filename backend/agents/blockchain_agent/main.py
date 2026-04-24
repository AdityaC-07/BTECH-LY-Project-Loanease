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

from core.session import session_store
from services.pdf_generator import generate_sanction_letter
from core.config import settings

logger = logging.getLogger("loanease.blockchain")

router = APIRouter()

# Global blockchain state
_ledger = []
_private_key = None
_public_key = None

# Pydantic models
class SanctionRequest(BaseModel):
    session_id: str
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

class VerifyRequest(BaseModel):
    reference_id: str

class VerifyResponse(BaseModel):
    valid: bool
    block_data: Dict[str, Any]
    verification_details: Dict[str, Any]

class ChainResponse(BaseModel):
    chain_length: int
    blocks: List[Dict[str, Any]]

class Block:
    def __init__(self, data: Dict[str, Any], previous_hash: str = "0"):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.data = data
        self.previous_hash = previous_hash
        self.nonce = 0
        self.hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """Calculate block hash"""
        block_string = json.dumps({
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }, sort_keys=True)
        
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def mine_block(self, difficulty: int):
        """Mine block with proof of work"""
        target = "0" * difficulty
        while self.hash[:difficulty] != target:
            self.nonce += 1
            self.hash = self.calculate_hash()

def init_ledger():
    """Initialize blockchain ledger"""
    global _ledger
    try:
        # Create genesis block
        genesis_data = {
            "type": "GENESIS",
            "message": "LoanEase Blockchain Initiated",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        genesis_block = Block(genesis_data)
        genesis_block.mine_block(settings.BLOCKCHAIN_DIFFICULTY)
        _ledger = [genesis_block]
        logger.info("Blockchain ledger initialized with genesis block")
    except Exception as e:
        logger.error(f"Failed to initialize ledger: {e}")
        _ledger = []

def ledger_ready() -> bool:
    """Check if ledger is ready"""
    return len(_ledger) > 0

def load_keys():
    """Load or generate RSA keys"""
    global _private_key, _public_key
    
    keys_dir = "keys"
    private_key_path = os.path.join(keys_dir, "private_key.pem")
    public_key_path = os.path.join(keys_dir, "public_key.pem")
    
    try:
        # Create keys directory if not exists
        os.makedirs(keys_dir, exist_ok=True)
        
        # Try to load existing keys
        if os.path.exists(private_key_path) and os.path.exists(public_key_path):
            with open(private_key_path, "rb") as f:
                _private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None
                )
            
            with open(public_key_path, "rb") as f:
                _public_key = serialization.load_pem_public_key(f.read())
            
            logger.info("RSA keys loaded from files")
        else:
            # Generate new keys
            _private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            _public_key = _private_key.public_key()
            
            # Save keys
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
            
            logger.info("New RSA keys generated and saved")
            
    except Exception as e:
        logger.error(f"Failed to load/generate keys: {e}")
        _private_key = None
        _public_key = None

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

def add_block_to_ledger(data: Dict[str, Any]) -> str:
    """Add new block to ledger"""
    global _ledger
    
    if not _ledger:
        raise RuntimeError("Ledger not initialized")
    
    try:
        # Get previous hash
        previous_hash = _ledger[-1].hash
        
        # Create new block
        new_block = Block(data, previous_hash)
        
        # Mine block
        new_block.mine_block(settings.BLOCKCHAIN_DIFFICULTY)
        
        # Add to ledger
        _ledger.append(new_block)
        
        return new_block.hash
        
    except Exception as e:
        logger.error(f"Failed to add block: {e}")
        raise

@router.post("/sanction", response_model=SanctionResponse)
async def create_sanction_letter(request: SanctionRequest):
    """Create blockchain-verified sanction letter"""
    try:
        # Get session
        session = session_store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Generate transaction ID
        import uuid
        transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        
        # Create sanction data
        sanction_data = {
            "transaction_id": transaction_id,
            "applicant_name": request.applicant_name,
            "pan_number": request.pan_number,
            "loan_amount": request.loan_amount,
            "interest_rate": request.interest_rate,
            "tenure_years": request.tenure_years,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "SANCTION_LETTER"
        }
        
        # Add to blockchain
        block_hash = add_block_to_ledger(sanction_data)
        
        # Sign the data
        data_string = json.dumps(sanction_data, sort_keys=True)
        signature = sign_data(data_string)
        
        # Generate PDF
        from services.emi import calculate_emi
        emi_result = calculate_emi(request.loan_amount, request.interest_rate, request.tenure_years)
        
        pdf_bytes = generate_sanction_letter(
            applicant_name=request.applicant_name,
            pan_number=request.pan_number,
            loan_amount=request.loan_amount,
            interest_rate=request.interest_rate,
            tenure_years=request.tenure_years,
            emi=emi_result["monthly_emi"],
            application_id=transaction_id
        )
        
        # Store PDF (in real app, would save to file system or cloud)
        # For now, we'll just return the reference
        
        # Update session
        session_store.update_stage(request.session_id, "BLOCKCHAIN_VERIFIED")
        session_store.update_data(request.session_id, "blockchain_data", {
            "transaction_id": transaction_id,
            "block_hash": block_hash,
            "signature": signature
        })
        session_store.log_agent(request.session_id, {
            "agent": "blockchain",
            "action": "sanction",
            "transaction_id": transaction_id,
            "block_hash": block_hash
        })
        
        return SanctionResponse(
            transaction_id=transaction_id,
            block_hash=block_hash,
            qr_code_url=f"/blockchain/qr/{transaction_id}",
            verification_url=f"/blockchain/verify/{transaction_id}",
            pdf_download_url=f"/blockchain/pdf/{transaction_id}"
        )
        
    except Exception as e:
        logger.error(f"Sanction letter creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sanction letter creation failed: {str(e)}")

@router.get("/verify/{reference_id}", response_model=VerifyResponse)
async def verify_document(reference_id: str):
    """Verify document on blockchain"""
    try:
        # Find block with this transaction ID
        target_block = None
        for block in _ledger:
            if block.data.get("transaction_id") == reference_id:
                target_block = block
                break
        
        if not target_block:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Verify signature
        data_string = json.dumps(target_block.data, sort_keys=True)
        signature = target_block.data.get("signature")
        
        signature_valid = False
        if signature:
            signature_valid = verify_signature(data_string, signature)
        
        # Verify blockchain integrity
        chain_valid = True
        for i in range(1, len(_ledger)):
            current_block = _ledger[i]
            previous_block = _ledger[i-1]
            
            if current_block.previous_hash != previous_block.hash:
                chain_valid = False
                break
            
            if current_block.hash != current_block.calculate_hash():
                chain_valid = False
                break
        
        verification_details = {
            "signature_valid": signature_valid,
            "blockchain_integrity": chain_valid,
            "block_number": _ledger.index(target_block),
            "timestamp": target_block.timestamp,
            "confirmations": len(_ledger) - _ledger.index(target_block)
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
        blocks_data = []
        for block in _ledger:
            blocks_data.append({
                "hash": block.hash,
                "timestamp": block.timestamp,
                "previous_hash": block.previous_hash,
                "nonce": block.nonce,
                "data": block.data
            })
        
        return ChainResponse(
            chain_length=len(_ledger),
            blocks=blocks_data
        )
        
    except Exception as e:
        logger.error(f"Failed to get blockchain: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get blockchain: {str(e)}")

@router.get("/health")
async def blockchain_health():
    """Blockchain service health check"""
    return {
        "status": "healthy" if ledger_ready() else "error",
        "ledger_ready": ledger_ready(),
        "chain_length": len(_ledger),
        "keys_loaded": _private_key is not None and _public_key is not None,
        "difficulty": settings.BLOCKCHAIN_DIFFICULTY
    }

from __future__ import annotations

import os
import json
import hashlib
import base64
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat


@dataclass
class Block:
    """Represents a single block in the blockchain"""
    index: int
    timestamp: str
    transaction_data: Dict[str, Any]
    previous_hash: str
    hash: str
    nonce: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert block to dictionary for JSON serialization"""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transaction_data": self.transaction_data,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "nonce": self.nonce
        }


class Blockchain:
    """Mock blockchain implementation with real cryptographic operations"""
    
    def __init__(self):
        self.chain: List[Block] = []
        self.create_genesis_block()
    
    def create_genesis_block(self):
        """Create the first block in the chain"""
        genesis_block = Block(
            index=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            transaction_data={
                "message": "LoanEase Genesis Block - Audit Ledger Initialized",
                "creator": "LoanEase AI System",
                "version": "1.0.0"
            },
            previous_hash="0" * 64,  # 64 zeros for genesis
            hash=self.compute_hash("genesis", "0" * 64, 0)
        )
        self.chain.append(genesis_block)
    
    def get_latest_block(self) -> Block:
        """Get the most recent block in the chain"""
        return self.chain[-1]
    
    def add_transaction(self, data: Dict[str, Any]) -> Block:
        """Add a new transaction as a block to the chain"""
        previous_block = self.get_latest_block()
        
        new_block = Block(
            index=len(self.chain),
            timestamp=datetime.now(timezone.utc).isoformat(),
            transaction_data=data,
            previous_hash=previous_block.hash,
            hash=""  # Will be computed
        )
        
        # Simple proof of work (find nonce that makes hash start with '00')
        new_block.hash = self.mine_block(new_block)
        self.chain.append(new_block)
        
        return new_block
    
    def mine_block(self, block: Block) -> str:
        """Simple proof-of-work: find nonce that makes hash start with '00'"""
        difficulty = 2  # Hash must start with '00'
        target = "0" * difficulty
        
        while True:
            block_hash = self.compute_block_hash(block)
            if block_hash.startswith(target):
                return block_hash
            block.nonce += 1
    
    def compute_block_hash(self, block: Block) -> str:
        """Compute SHA-256 hash of block content"""
        block_string = json.dumps({
            "index": block.index,
            "timestamp": block.timestamp,
            "data": block.transaction_data,
            "previous_hash": block.previous_hash,
            "nonce": block.nonce
        }, sort_keys=True)
        
        return hashlib.sha256(block_string.encode('utf-8')).hexdigest()
    
    def compute_hash(self, content: str, previous_hash: str, nonce: int) -> str:
        """Compute hash for content (used for genesis block)"""
        data_string = json.dumps({
            "content": content,
            "previous_hash": previous_hash,
            "nonce": nonce
        }, sort_keys=True)
        
        return hashlib.sha256(data_string.encode('utf-8')).hexdigest()
    
    def is_chain_valid(self) -> bool:
        """Verify the entire chain is valid"""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i-1]
            
            # Verify current block's hash
            if current.hash != self.compute_block_hash(current):
                return False
            
            # Verify linkage to previous block
            if current.previous_hash != previous.hash:
                return False
        
        return True
    
    def get_transaction(self, tx_id: str) -> Optional[Block]:
        """Find a transaction by ID"""
        for block in self.chain:
            if block.transaction_data.get("transaction_id") == tx_id:
                return block
        return None
    
    def get_transaction_by_reference(self, reference: str) -> Optional[Block]:
        """Find a transaction by sanction reference"""
        for block in self.chain:
            if block.transaction_data.get("sanction_reference") == reference:
                return block
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get blockchain statistics"""
        sanction_blocks = [b for b in self.chain[1:] if "sanction_reference" in b.transaction_data]
        total_amount = sum(b.transaction_data.get("loan_amount", 0) for b in sanction_blocks)
        
        return {
            "total_sanctions": len(sanction_blocks),
            "total_amount_sanctioned": total_amount,
            "chain_valid": self.is_chain_valid(),
            "genesis_timestamp": self.chain[0].timestamp,
            "latest_block_timestamp": self.get_latest_block().timestamp,
            "chain_length": len(self.chain)
        }


class CryptoManager:
    """Handles cryptographic operations for the blockchain"""
    
    def __init__(self, keys_dir: str = "keys"):
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(exist_ok=True)
        
        self.private_key_path = self.keys_dir / "private_key.pem"
        self.public_key_path = self.keys_dir / "public_key.pem"
        
        # Generate or load keys
        self.private_key, self.public_key = self._initialize_keys()
    
    def _initialize_keys(self) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
        """Generate new keys or load existing ones"""
        if self.private_key_path.exists() and self.public_key_path.exists():
            return self._load_keys()
        else:
            return self._generate_keys()
    
    def _generate_keys(self) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
        """Generate new RSA 2048-bit key pair"""
        print("🔐 Generating new RSA key pair for LoanEase...")
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        public_key = private_key.public_key()
        
        # Save keys to files
        self._save_keys(private_key, public_key)
        
        print("✅ RSA key pair generated and saved to keys/ directory")
        return private_key, public_key
    
    def _save_keys(self, private_key: rsa.RSAPrivateKey, public_key: rsa.RSAPublicKey):
        """Save keys to PEM files"""
        # Save private key
        private_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        )
        
        with open(self.private_key_path, 'wb') as f:
            f.write(private_pem)
        
        # Save public key
        public_pem = public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo
        )
        
        with open(self.public_key_path, 'wb') as f:
            f.write(public_pem)
    
    def _load_keys(self) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
        """Load existing keys from PEM files"""
        # Load private key
        with open(self.private_key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None
            )
        
        # Load public key
        with open(self.public_key_path, 'rb') as f:
            public_key = serialization.load_pem_public_key(
                f.read()
            )
        
        print("🔑 Loaded existing RSA keys from keys/ directory")
        return private_key, public_key
    
    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def sign_document(self, content: str) -> str:
        """Sign content with RSA private key"""
        signature = self.private_key.sign(
            content.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return base64.b64encode(signature).decode('utf-8')
    
    def verify_signature(self, content: str, signature_b64: str) -> bool:
        """Verify signature using public key"""
        try:
            signature = base64.b64decode(signature_b64)
            
            self.public_key.verify(
                signature,
                content.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
        except Exception:
            return False
    
    def get_public_key_pem(self) -> str:
        """Get public key as PEM string"""
        public_pem = self.public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo
        )
        return public_pem.decode('utf-8')


# Global instances
crypto_manager = CryptoManager()
ledger = Blockchain()

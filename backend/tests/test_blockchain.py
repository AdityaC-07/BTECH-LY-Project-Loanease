from __future__ import annotations

import hashlib
import json

import pytest

from services.merkle_tree import MerkleTree
from services.enhanced_blockchain import (
    EnhancedBlockchain,
    Block,
    DIFFICULTY,
)


class TestMerkleTree:
    def test_single_transaction(self):
        tree = MerkleTree([{"tx": "test"}])
        assert tree.root is not None
        assert len(tree.root) == 64

    def test_multiple_transactions(self):
        transactions = [
            {"id": 1, "data": "tx1"},
            {"id": 2, "data": "tx2"},
            {"id": 3, "data": "tx3"},
            {"id": 4, "data": "tx4"},
        ]
        tree = MerkleTree(transactions)
        assert tree.root is not None
        assert tree.get_tree_size() == 4

    def test_empty_transactions(self):
        tree = MerkleTree([])
        assert tree.root is not None

    def test_odd_number_of_transactions(self):
        transactions = [
            {"id": 1, "data": "tx1"},
            {"id": 2, "data": "tx2"},
            {"id": 3, "data": "tx3"},
        ]
        tree = MerkleTree(transactions)
        assert tree.root is not None

    def test_hash_is_sha256(self):
        tree = MerkleTree([{"tx": "test"}])
        assert len(tree.root) == 64
        int(tree.root, 16)

    def test_different_transactions_different_roots(self):
        tree_1 = MerkleTree([{"data": "hello"}])
        tree_2 = MerkleTree([{"data": "world"}])
        assert tree_1.root != tree_2.root

    def test_same_transactions_same_root(self):
        tree_1 = MerkleTree([{"data": "test"}])
        tree_2 = MerkleTree([{"data": "test"}])
        assert tree_1.root == tree_2.root

    def test_get_proof_valid_index(self):
        transactions = [{"id": i} for i in range(4)]
        tree = MerkleTree(transactions)
        proof = tree.get_proof(0)
        assert len(proof) >= 1

    def test_get_proof_invalid_index(self):
        tree = MerkleTree([{"id": 1}])
        with pytest.raises(IndexError):
            tree.get_proof(5)

    def test_verify_proof_valid(self):
        transactions = [{"id": i} for i in range(4)]
        tree = MerkleTree(transactions)
        leaf_hash = tree.get_leaf_hash(0)
        proof = tree.get_proof(0)
        assert MerkleTree.verify_proof(leaf_hash, proof, tree.root)

    def test_verify_proof_invalid(self):
        transactions = [{"id": i} for i in range(4)]
        tree = MerkleTree(transactions)
        leaf_hash = tree.get_leaf_hash(0)
        proof = tree.get_proof(0)
        assert not MerkleTree.verify_proof(leaf_hash + "x", proof, tree.root)

    def test_to_dict_and_from_dict(self):
        transactions = [{"id": 1, "data": "test"}]
        tree = MerkleTree(transactions)
        data = tree.to_dict()
        restored = MerkleTree.from_dict(data)
        assert restored.root == tree.root
        assert restored.get_tree_size() == tree.get_tree_size()


class TestBlock:
    def test_block_creation(self):
        block = Block(
            index=1,
            timestamp="2024-01-01T00:00:00",
            previous_hash="0" * 64,
            transactions=[{"tx": "test"}],
            merkle_root="abc",
        )
        assert block.index == 1
        assert block.hash == ""

    def test_compute_hash(self):
        block = Block(
            index=1,
            timestamp="2024-01-01T00:00:00",
            previous_hash="0" * 64,
            transactions=[{"tx": "test"}],
            merkle_root="abc",
        )
        h = block.compute_hash()
        assert len(h) == 64
        int(h, 16)

    def test_mine_block_produces_valid_hash(self):
        block = Block(
            index=0,
            timestamp="2024-01-01T00:00:00",
            previous_hash="0" * 64,
            transactions=[{"tx": "test"}],
            merkle_root="abc",
        )
        block.mine_block()
        assert block.hash.startswith("0" * DIFFICULTY)
        assert block.nonce >= 0

    def test_to_dict(self):
        block = Block(
            index=1,
            timestamp="2024-01-01T00:00:00",
            previous_hash="0" * 64,
            transactions=[{"tx": "test"}],
            merkle_root="abc",
            nonce=42,
            hash="xyz",
        )
        data = block.to_dict()
        assert data["index"] == 1
        assert data["nonce"] == 42
        assert data["hash"] == "xyz"


class TestEnhancedBlockchain:
    def test_genesis_block_created(self):
        chain = EnhancedBlockchain()
        assert len(chain.chain) == 1
        assert chain.chain[0].index == 0

    def test_genesis_block_mined(self):
        chain = EnhancedBlockchain()
        genesis = chain.chain[0]
        assert genesis.hash.startswith("0" * DIFFICULTY)

    def test_add_transaction(self):
        chain = EnhancedBlockchain()
        tx = {"transaction_type": "SANCTION", "reference": "TEST-001"}
        block = chain.add_transaction(tx)
        assert block.index == 1
        assert len(chain.chain) == 2

    def test_add_multiple_transactions(self):
        chain = EnhancedBlockchain()
        for i in range(3):
            chain.add_transaction({"reference": f"TEST-00{i}"})
        assert len(chain.chain) == 4

    def test_chain_integrity_valid(self):
        chain = EnhancedBlockchain()
        for i in range(3):
            chain.add_transaction({"reference": f"TEST-00{i}"})
        assert chain.verify_chain_integrity()

    def test_chain_integrity_tampered(self):
        chain = EnhancedBlockchain()
        chain.add_transaction({"reference": "TEST-001"})
        chain.chain[1].transactions[0]["reference"] = "TAMPERED"
        assert not chain.verify_chain_integrity()

    def test_find_transaction_by_reference(self):
        chain = EnhancedBlockchain()
        chain.add_transaction({"reference": "SANCTION-001"})
        result = chain.find_transaction_by_reference("SANCTION-001")
        assert result is not None
        assert result["found_in_block"] == 1

    def test_find_nonexistent_transaction(self):
        chain = EnhancedBlockchain()
        result = chain.find_transaction_by_reference("NONEXISTENT")
        assert result is None

    def test_amend_sanction(self):
        chain = EnhancedBlockchain()
        chain.add_transaction({"reference": "SANC-001"})
        amendment = chain.amend_sanction("SANC-001", {"rate": 11.0}, "Customer request")
        assert amendment.index == 2
        assert amendment.transactions[0]["transaction_type"] == "AMENDMENT"

    def test_get_merkle_proof(self):
        chain = EnhancedBlockchain()
        chain.add_transaction({"reference": "TX-001"})
        proof = chain.get_merkle_proof("TX-001")
        assert proof is not None
        assert "proof" in proof
        assert "merkle_root" in proof

    def test_get_chain_summary(self):
        chain = EnhancedBlockchain()
        chain.add_transaction({"transaction_type": "SANCTION", "loan_amount": 500000})
        summary = chain.get_chain_summary()
        assert summary["total_blocks"] == 2
        assert summary["total_sanctions"] == 1
        assert summary["total_amount_sanctioned"] == 500000
        assert summary["chain_valid"] is True

    def test_get_explorer_data(self):
        chain = EnhancedBlockchain()
        data = chain.get_explorer_data()
        assert "chain_summary" in data
        assert "blocks" in data
        assert len(data["blocks"]) >= 1

    def test_validate_document_hash_valid(self):
        chain = EnhancedBlockchain()
        doc_content = "Sanction Letter Content"
        doc_hash = hashlib.sha256(doc_content.encode()).hexdigest()
        chain.add_transaction({
            "reference": "DOC-001",
            "document_hash": doc_hash,
        })
        result = chain.validate_document_hash(doc_content, "DOC-001")
        assert result["valid"] is True

    def test_validate_document_hash_tampered(self):
        chain = EnhancedBlockchain()
        doc_hash = hashlib.sha256("Original".encode()).hexdigest()
        chain.add_transaction({
            "reference": "DOC-001",
            "document_hash": doc_hash,
        })
        result = chain.validate_document_hash("Tampered", "DOC-001")
        assert result["valid"] is False
        assert "mismatch" in result["reason"].lower()

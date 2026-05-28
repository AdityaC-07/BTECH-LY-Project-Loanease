import React, { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Database, Activity, Lock, Layers, Info, X, ExternalLink, ShieldCheck, Link as LinkIcon, Search, CheckCircle2, AlertCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { BlockCard } from "@/components/blockchain/BlockCard";
import { MerkleTree } from "@/components/blockchain/MerkleTree";
import { TamperDemo } from "@/components/blockchain/TamperDemo";
import { cn } from "@/lib/utils";
import { API_BASE_URL } from "@/config";

export default function BlockchainExplorer() {
  // Helper function to format block timestamps
  const formatBlockTime = (timestamp: string | undefined): string => {
    if (!timestamp) return 'Unknown'
    try {
      const d = new Date(timestamp)
      if (isNaN(d.getTime())) {
        // Try parsing as ISO string
        return timestamp.split('T')[0] || 'Invalid Date'
      }
      return d.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      }) + ' ' + d.toLocaleTimeString('en-IN', { 
        hour: '2-digit', 
        minute: '2-digit' 
      })
    } catch {
      return 'Unknown'
    }
  }
  const [data, setData] = useState<any>(null);
  const [selectedBlock, setSelectedBlock] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tamperResult, setTamperResult] = useState<any>(null);
  const [isBroken, setIsBroken] = useState(false);
  const [txnSearch, setTxnSearch] = useState("");
  const [txnVerification, setTxnVerification] = useState<any>(null);
  const [txnLoading, setTxnLoading] = useState(false);
  const [pendingAutoVerify, setPendingAutoVerify] = useState<string | null>(null);
  const searchSectionRef = useRef<HTMLDivElement | null>(null);
  const resultSectionRef = useRef<HTMLDivElement | null>(null);

  const formatCurrency = (value: any): string => {
    if (value === undefined || value === null || value === "") return "—";
    const numberValue = Number(value);
    if (Number.isNaN(numberValue)) return String(value);
    return `₹${numberValue.toLocaleString("en-IN")}`;
  };

  const renderResultField = (label: string, value: any) => (
    <div className="rounded-md border border-white/5 bg-black/60 p-4">
      <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div className="break-words font-mono text-sm text-white">{value ?? "—"}</div>
    </div>
  );

  const fetchData = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/blockchain/explorer-data`);
      const json = await response.json();
      setData(json);
      if (json.blocks.length > 0 && !selectedBlock) {
        setSelectedBlock(json.blocks[json.blocks.length - 1]);
      }
      setLoading(false);
    } catch (error) {
      console.error("Failed to fetch explorer data", error);
      setLoading(false);
    }
  };

  async function verifyTransaction(overrideTxnId?: string) {
    const txnId = (overrideTxnId ?? txnSearch).trim();

    if (!txnId) {
      return;
    }

    setTxnLoading(true);
    setTxnVerification(null);

    try {
      const response = await fetch(`${API_BASE_URL}/blockchain/verify/${encodeURIComponent(txnId)}`);
      const data = await response.json();
      setTxnVerification(data);
      window.setTimeout(() => {
        resultSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 50);
    } catch (error) {
      console.error("Failed to verify transaction", error);
      setTxnVerification({
        found: false,
        authentic: false,
        txn_id: txnId,
        status: "ERROR",
        message: "Could not connect to the ledger. Please try again.",
        risk_level: "HIGH",
      });
      window.setTimeout(() => {
        resultSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 50);
    } finally {
      setTxnLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const autoVerify = params.get("verify");

    if (!autoVerify) {
      return;
    }

    setPendingAutoVerify(autoVerify);
    setTxnSearch(autoVerify);
    const timer = window.setTimeout(() => {
      void verifyTransaction(autoVerify);
    }, 500);

    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!loading && pendingAutoVerify) {
      searchSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      setPendingAutoVerify(null);
    }
  }, [loading, pendingAutoVerify]);

  const handleTamper = (result: any) => {
    setTamperResult(result);
    setIsBroken(true);
  };

  const handleReset = () => {
    setTamperResult(null);
    setIsBroken(false);
    fetchData();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Activity className="w-12 h-12 text-[hsl(47,100%,50%)] animate-pulse" />
          <p className="text-[hsl(47,100%,50%)] font-mono text-sm tracking-widest uppercase">Initializing Ledger Explorer...</p>
        </div>
      </div>
    );
  }

  const stats = data?.chain_stats || {};
  const blocks = data?.blocks || [];
  const merkleTrees = data?.merkle_trees || {};

  // Find the latest sanction reference for the tamper demo
  const latestSanction = blocks.slice().reverse().find((b: any) => 
    b.block_type === "SANCTION" || 
    (b.transaction_data && (b.transaction_data.type === "SANCTION_LETTER" || b.transaction_data.sanction_reference))
  );
  const sanctionRef = latestSanction?.transaction_data?.sanction_reference || latestSanction?.transaction_data?.transaction_id;

  const verificationResult = txnVerification;
  const isAuthentic = Boolean(verificationResult?.authentic);
  const isNotFound = verificationResult?.found === false || verificationResult?.status === "ERROR";
  const isTampered = verificationResult?.found && !verificationResult?.authentic;

  return (
    <div className="min-h-screen bg-black text-white font-sans selection:bg-[hsl(47,100%,50%)] selection:text-black">
      {/* Header */}
      <header className="border-b border-[hsl(0,0%,15%)] bg-black/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-[1400px] mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="p-2 hover:bg-white/5 rounded-full transition-colors group">
              <ChevronLeft className="group-hover:-translate-x-1 transition-transform" />
            </Link>
            <div>
              <h1 className="text-2xl font-black flex items-center gap-3 uppercase tracking-tighter">
                <span className="text-3xl"><LinkIcon className="w-8 h-8" /></span> LoanEase Audit Ledger
              </h1>
              <p className="text-[10px] text-muted-foreground uppercase tracking-[0.2em] font-bold">
                Tamper-evident blockchain record of all sanctioned loans
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full border text-[10px] font-bold uppercase tracking-widest",
              !isBroken ? "bg-green-500/10 border-green-500/20 text-green-400" : "bg-red-500/10 border-red-500/20 text-red-400"
            )}>
              <div className={cn("w-1.5 h-1.5 rounded-full", !isBroken ? "bg-green-500 animate-pulse" : "bg-red-500")} />
              {isBroken ? "Chain Invalid" : "System Synchronized"}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-12 space-y-12">
        {/* Transaction Verification */}
        <section
          ref={searchSectionRef}
          className="rounded-3xl border border-[#1a1a1a] bg-[#0a0a0a] px-6 py-10 text-center shadow-[0_24px_80px_rgba(0,0,0,0.35)] md:px-10"
        >
          <h2 className="mb-2 text-3xl font-black uppercase tracking-tighter md:text-4xl">Verify a Transaction</h2>
          <p className="mx-auto mb-8 max-w-2xl text-sm text-muted-foreground md:text-base">
            Enter any Transaction ID from a LoanEase sanction letter to verify its authenticity.
          </p>

          <div className="mx-auto flex max-w-3xl flex-col gap-3 sm:flex-row sm:gap-0">
            <input
              id="txnSearchInput"
              type="text"
              value={txnSearch}
              onChange={(event) => setTxnSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void verifyTransaction();
                }
              }}
              placeholder="TXN-5ED5818EE05D"
              spellCheck={false}
              autoComplete="off"
              className="w-full rounded-md border border-[#2a2a2a] bg-[#111] px-5 py-4 font-mono text-[15px] tracking-[0.08em] text-[hsl(47,100%,50%)] outline-none transition-colors placeholder:text-[#333] focus:border-[hsl(47,100%,50%)] sm:rounded-r-none"
            />
            <button
              id="txnVerifyBtn"
              type="button"
              onClick={() => void verifyTransaction()}
              disabled={txnLoading}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-[hsl(47,100%,50%)] px-8 py-4 text-sm font-bold tracking-[0.2em] text-black transition-colors hover:bg-[#e6b800] disabled:cursor-not-allowed disabled:bg-[#333] disabled:text-[#666] sm:rounded-l-none"
            >
              <Search className="h-4 w-4" />
              {txnLoading ? "VERIFYING..." : "VERIFY"}
            </button>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-center gap-2 text-sm text-muted-foreground">
            <span>Examples:</span>
            <button
              type="button"
              onClick={() => {
                setTxnSearch("TXN-5ED5818EE05D");
                void verifyTransaction("TXN-5ED5818EE05D");
              }}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1 font-mono text-[13px] text-[hsl(47,100%,50%)] transition-colors hover:border-[hsl(47,100%,50%)]"
            >
              TXN-5ED5818EE05D
            </button>
          </div>

          <div ref={resultSectionRef} className="mt-8">
            {verificationResult && isAuthentic && (
              <div className="result-authentic rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-6 text-left">
                <div className="result-status flex items-center gap-3 text-2xl font-black uppercase tracking-tight text-emerald-400 md:text-3xl">
                  <CheckCircle2 className="h-7 w-7" />
                  Transaction Verified
                </div>
                <p className="mt-2 text-sm text-zinc-300">
                  This transaction is authentic and recorded in the immutable LoanEase ledger.
                </p>
                <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
                  {renderResultField("Transaction ID", verificationResult.txn_id)}
                  {renderResultField("Status", verificationResult.status)}
                  {renderResultField("Block", verificationResult.block_index !== undefined ? `#${verificationResult.block_index}` : "—")}
                  {renderResultField("Applicant", verificationResult.applicant_name || "—")}
                  {renderResultField("Loan Amount", formatCurrency(verificationResult.loan_amount))}
                  {renderResultField("Interest Rate", verificationResult.interest_rate !== undefined && verificationResult.interest_rate !== null ? `${verificationResult.interest_rate}% p.a.` : "—")}
                  {renderResultField("Sanction Date", verificationResult.sanction_date ? formatBlockTime(verificationResult.sanction_date) : "—")}
                  {renderResultField("Block Hash", verificationResult.block_hash ? `${verificationResult.block_hash.slice(0, 20)}...` : "—")}
                  {renderResultField("Merkle Root", verificationResult.merkle_root ? `${verificationResult.merkle_root.slice(0, 20)}...` : "—")}
                  {renderResultField("Chain Valid", verificationResult.chain_valid ? "Yes" : "No")}
                  {renderResultField("Block Hash Valid", verificationResult.block_hash_valid ? "Yes" : "No")}
                  {renderResultField("Merkle Valid", verificationResult.merkle_root_valid ? "Yes" : "No")}
                </div>
                <div className="mt-4 rounded-md border border-white/10 bg-[#0d0d0d] p-3 text-xs text-zinc-500">
                  ✓ Chain integrity verified to Block #{verificationResult.block_index} &nbsp; ✓ Block hash valid &nbsp; ✓ Merkle tree intact
                </div>
              </div>
            )}

            {verificationResult && isNotFound && (
              <div className="result-not-found rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-left">
                <div className="result-status flex items-center gap-3 text-2xl font-black uppercase tracking-tight text-red-400 md:text-3xl">
                  <X className="h-7 w-7" />
                  {verificationResult.status === "ERROR" ? "Verification Failed" : "Not Found"}
                </div>
                <p className="mt-2 text-sm text-zinc-300">
                  {verificationResult.message}
                </p>
                <div className="mt-4 rounded-md border border-white/10 bg-[#0d0d0d] p-4 text-sm text-zinc-400">
                  This could mean the document is forged, the Transaction ID was altered, or the loan was not processed through LoanEase.
                </div>
              </div>
            )}

            {verificationResult && isTampered && (
              <div className="result-tampered rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6 text-left">
                <div className="result-status flex items-center gap-3 text-2xl font-black uppercase tracking-tight text-amber-400 md:text-3xl">
                  <AlertCircle className="h-7 w-7" />
                  Integrity Failure
                </div>
                <p className="mt-2 text-sm text-zinc-300">
                  Transaction found but blockchain integrity check failed. This document may have been tampered with after issuance.
                </p>
                <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                  {renderResultField("Transaction ID", verificationResult.txn_id)}
                  {renderResultField("Status", verificationResult.status)}
                  {renderResultField("Block", verificationResult.block_index !== undefined ? `#${verificationResult.block_index}` : "—")}
                  {renderResultField("Chain Valid", verificationResult.chain_valid ? "Yes" : "No")}
                  {renderResultField("Block Hash Valid", verificationResult.block_hash_valid ? "Yes" : "No")}
                  {renderResultField("Merkle Valid", verificationResult.merkle_root_valid ? "Yes" : "No")}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Stats Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {[
            { label: "Total Blocks", value: stats.total_blocks || 0, icon: Database, color: "text-blue-400" },
            { label: "Active Sanctions", value: stats.active_sanctions || 0, icon: Lock, color: "text-[hsl(47,100%,50%)]" },
            { label: "Chain Status", value: stats.chain_valid ? "VERIFIED" : "INVALID", icon: ShieldCheck, color: stats.chain_valid ? "text-green-500" : "text-red-500" },
            { label: "PoW Difficulty", value: `Level ${stats.pow_difficulty || 2}`, icon: Activity, color: "text-purple-400" }
          ].map((stat, i) => (
            <Card key={i} className="bg-[hsl(0,0%,7%)] border-[hsl(0,0%,15%)] hover:border-[hsl(0,0%,25%)] transition-colors">
              <CardContent className="p-6 flex items-center gap-4">
                <div className={cn("p-3 rounded-xl bg-white/5", stat.color)}>
                  <stat.icon size={24} />
                </div>
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-1">{stat.label}</p>
                  <p className="text-2xl font-black tracking-tight">{stat.value}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Blockchain Visualizer */}
        <section className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Layers className="text-[hsl(47,100%,50%)]" size={24} />
              Immutable Chain Visualization
            </h2>
            <div className="text-[10px] text-muted-foreground uppercase tracking-widest">
              Scroll horizontally to explore
            </div>
          </div>

          <div className="bg-[hsl(0,0%,5%)] border border-[hsl(0,0%,15%)] rounded-3xl p-10 overflow-x-auto custom-scrollbar">
            {blocks.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-400">
                <div className="text-center">
                  <Database className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p className="text-sm">No blocks yet. Complete a loan to see the chain.</p>
                </div>
              </div>
            ) : (
              <div className="flex min-w-max pb-4">
                {blocks.map((block: any, idx: number) => {
                  // If chain is broken at this index or after
                  const blockValid = !isBroken || idx < (latestSanction?.index || 0);
                  return (
                    <BlockCard 
                      key={idx}
                      block={block}
                      isValid={blockValid}
                      onDetailsClick={setSelectedBlock}
                      isLast={idx === blocks.length - 1}
                    />
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {/* Selected Block Details & Merkle Tree */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Details Sidebar */}
          <div className="lg:col-span-1 space-y-8">
            <Card className="bg-[hsl(0,0%,7%)] border-[hsl(0,0%,15%)] overflow-hidden">
              <div className="bg-[hsl(47,100%,50%)] h-1" />
              <CardContent className="p-8">
                <h3 className="text-lg font-bold mb-6 flex items-center justify-between">
                  Block Details
                  <span className="text-xs font-mono text-muted-foreground">#{selectedBlock?.index}</span>
                </h3>
                
                <div className="space-y-6">
                  {[
                    { label: "Timestamp", value: formatBlockTime(selectedBlock?.timestamp) },
                    { label: "Block Type", value: selectedBlock?.block_type || (selectedBlock?.index === 0 ? "GENESIS" : "TRANSACTION") },
                    { label: "Transactions", value: selectedBlock?.transaction_count || (selectedBlock?.index === 0 ? "3 (Simulated)" : "1") },
                    { label: "Nonce", value: selectedBlock?.nonce || 0 },
                    { label: "Merkle Root", value: (selectedBlock?.merkle_root || "").slice(0, 16) + "..." || "—" },
                  ].map((row, i) => (
                    <div key={i} className="border-b border-white/5 pb-4 last:border-0">
                      <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-1">{row.label}</p>
                      <p className="text-sm font-mono text-white">{row.value}</p>
                    </div>
                  ))}
                  
                  <div className="pt-4">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-3">Transaction Content</p>
                    <pre className="bg-black p-4 rounded-xl border border-white/5 text-[10px] text-[hsl(47,100%,50%)] overflow-x-auto">
                      {JSON.stringify(selectedBlock?.transaction_data, null, 2)}
                    </pre>
                  </div>
                </div>
              </CardContent>
            </Card>

            <TamperDemo 
              sanctionReference={sanctionRef}
              onTamper={handleTamper}
              onReset={handleReset}
            />
          </div>

          {/* Merkle Tree Main View */}
          <div className="lg:col-span-2">
            {selectedBlock && (
              <MerkleTree 
                blockIndex={selectedBlock.index}
                treeData={merkleTrees[selectedBlock.index.toString()]}
              />
            )}
            
            {/* Legend/Info */}
            <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 bg-white/5 rounded-xl border border-white/10 flex gap-4">
                <div className="p-2 bg-[hsl(47,100%,50%)]/10 rounded-lg h-fit">
                  <Info className="text-[hsl(47,100%,50%)]" size={20} />
                </div>
                <div>
                  <h4 className="text-sm font-bold mb-1">How it works</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    This ledger uses SHA-256 hashing and ECDSA signatures. 
                    Each block "seals" the previous one, creating a chain 
                    where tampering is mathematically impossible without 
                    re-calculating every subsequent hash.
                  </p>
                </div>
              </div>
              <div className="p-4 bg-white/5 rounded-xl border border-white/10 flex gap-4">
                <div className="p-2 bg-blue-500/10 rounded-lg h-fit">
                  <ExternalLink className="text-blue-400" size={20} />
                </div>
                <div>
                  <h4 className="text-sm font-bold mb-1">Verify Manually</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    You can verify any sanction letter by entering its 
                    Transaction ID on this page. The system will locate 
                    the block and verify the cryptographic signature.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer Info */}
      <footer className="border-t border-[hsl(0,0%,15%)] py-12 px-6">
        <div className="max-w-[1400px] mx-auto flex flex-col md:flex-row justify-between items-center gap-6">
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold">
            LoanEase Audit Explorer v1.2 • Distributed Ledger Technology
          </p>
          <div className="flex gap-8">
            {["Protocol", "Consensus", "Cryptography", "Nodes"].map(item => (
              <span key={item} className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold hover:text-white cursor-help">
                {item}
              </span>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}


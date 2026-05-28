# Demo signer key — DO NOT REUSE FOR REAL EVIDENCE

`demo-signer.key` / `demo-signer.pub` are a **DEMO-ONLY** ed25519 keypair
(raw 32-byte seed, hex-encoded), committed so anyone cloning the repo can
reproduce the signed golden packet deterministically and run THE TAMPER PROOF.

This mirrors Reef's committed `quote/samples/sample-signer.key` convention: a
public, reproducible demo key — never a real operator key. A real Amber
deployment generates a fresh keypair (`amber.signer.generate_keypair`) and
keeps the private key outside the repo (the project `.gitignore` excludes
`*.key` except this one explicitly-labelled demo key).

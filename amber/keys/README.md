# Amber signer keys

This directory holds the signer key material `verify_packet` pins against.

| File | Committed? | What it is |
|---|---|---|
| `trusted_signers.txt` | **yes** (public) | allowlist of authorized signer ed25519 **public** keys; `verify_packet` pins the signature to a key in this set |
| `demo-signer.pub` | **yes** (public) | the demo signer's **public** key (also listed in the allowlist) |
| `demo-signer.key` | **NO — gitignored** | the demo signer's **PRIVATE** key (raw 32-byte seed, hex). Sealing needs it; verifying never does. |

## Why the private key is NOT committed

Verification needs **only the public key**. The signature is checked against the
trusted **public** key supplied out-of-band (the committed allowlist, or
`--pubkey` / `AMBER_TRUSTED_PUBKEY`). Committing the **private** key would let
anyone who reads the repo forge a packet (edit a fact → recompute the root →
re-sign with the real key → still in the trusted set → GREEN). So the private
key is gitignored. A fresh clone still verifies the committed golden packet
GREEN because that needs only the committed public key.

## Sealing (operator action — needs the secret)

`scripts/build_real_packet.py` loads the private key from, in order:

1. env `AMBER_SIGNING_KEY` (64-char hex ed25519 seed), else
2. the gitignored local file `amber/keys/demo-signer.key`.

Generate a fresh keypair and pin its public key:

```bash
python -c "from amber.signer import generate_keypair; sk,pk=generate_keypair(); print('private:',sk); print('public :',pk)"
# write the private key to amber/keys/demo-signer.key (gitignored) or export AMBER_SIGNING_KEY
# add the public key as a line in amber/keys/trusted_signers.txt
```

These are **DEMO-ONLY** keys — never a real operator key. A real Amber
deployment generates its own keypair, keeps the private key in secret storage,
and distributes the public key to verifiers out-of-band.

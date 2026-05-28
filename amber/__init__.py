"""Amber — forensically-signed, geo-attributed observations of public web state.

Component 1: the signed-provenance primitive + the offline ``verify_packet``
verifier. The signed bundle commits to raw captured bytes + Layer-1
deterministic facts via an RFC 6962 Merkle tree whose root is ed25519-signed.
"""

from amber.packet import CaptureInput, VerifyResult, seal_packet, verify_packet

__all__ = ["CaptureInput", "VerifyResult", "seal_packet", "verify_packet"]
__version__ = "0.1.0"

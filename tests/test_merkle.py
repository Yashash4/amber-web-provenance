"""Merkle tree primitive tests (RFC 6962 domain separation + lone-node promotion)."""

from __future__ import annotations

import hashlib

import pytest

from amber import merkle


def test_leaf_hash_domain_separated():
    """Leaf hash uses the 0x00 prefix (defends against second-preimage)."""
    data = b"hello"
    expected = hashlib.sha256(b"\x00" + data).digest()
    assert merkle.leaf_hash(data) == expected
    # A leaf hash must NOT equal a bare sha256 of the same bytes.
    assert merkle.leaf_hash(data) != hashlib.sha256(data).digest()


def test_internal_hash_domain_separated():
    left = merkle.leaf_hash(b"a")
    right = merkle.leaf_hash(b"b")
    expected = hashlib.sha256(b"\x01" + left + right).digest()
    assert merkle.internal_hash(left, right) == expected


def test_single_leaf_root_is_the_leaf():
    leaf = merkle.leaf_hash(b"only")
    assert merkle.merkle_root([leaf]) == leaf


def test_two_leaf_root():
    a = merkle.leaf_hash(b"a")
    b = merkle.leaf_hash(b"b")
    assert merkle.merkle_root([a, b]) == merkle.internal_hash(a, b)


def test_three_leaf_promotes_lone_node():
    """An odd third leaf is promoted, not hashed with itself."""
    a, b, c = (merkle.leaf_hash(x) for x in (b"a", b"b", b"c"))
    # level 0: [a,b,c] -> level 1: [H(a,b), c] -> root H(H(a,b), c)
    expected = merkle.internal_hash(merkle.internal_hash(a, b), c)
    assert merkle.merkle_root([a, b, c]) == expected


def test_root_changes_when_any_leaf_changes():
    leaves = [merkle.leaf_hash(x) for x in (b"a", b"b", b"c", b"d")]
    root0 = merkle.merkle_root(leaves)
    leaves[2] = merkle.leaf_hash(b"c-tampered")
    assert merkle.merkle_root(leaves) != root0


def test_root_is_order_sensitive():
    a, b = merkle.leaf_hash(b"a"), merkle.leaf_hash(b"b")
    assert merkle.merkle_root([a, b]) != merkle.merkle_root([b, a])


def test_empty_tree_raises():
    with pytest.raises(ValueError):
        merkle.merkle_root([])


def test_known_vector_two_leaves_hex():
    """Pin a concrete hex vector so a future refactor can't silently drift."""
    a = merkle.leaf_hash(b"x")
    b = merkle.leaf_hash(b"y")
    root = merkle.merkle_root_hex([a, b])
    recompute = hashlib.sha256(b"\x01" + a + b).hexdigest()
    assert root == recompute
    assert len(root) == 64

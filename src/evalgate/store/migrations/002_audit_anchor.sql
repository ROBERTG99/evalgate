-- 002_audit_anchor: when retention prunes the head of gate_audit, the last pruned row's seq and hash
-- are kept so verification can tell retention from tampering.
CREATE TABLE IF NOT EXISTS audit_anchor (
    seq BIGINT PRIMARY KEY,
    hash VARCHAR NOT NULL,
    pruned_at TIMESTAMP NOT NULL
);

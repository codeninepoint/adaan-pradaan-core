# Phase 2 allocation state machine (minimal foundation)

```mermaid
stateDiagram-v2
  [*] --> requested
  requested --> allocated: authorize_and_quota_ok
  requested --> rejected: quota_or_authz_fail
  allocated --> released: release
  rejected --> [*]
  released --> [*]
```

## Extension points (later)

- Add `pending_approval` and `approved` for human approval flows.
- Add `failed` if provisioning (Kubernetes/cloud) is introduced.


# OpenShift Virtualization Storage Management Tools

## Problem Statement

OpenShift Virtualization's storage management has significant storage class migration challenges:

- **Manual storage migration**: Updating storage classes requires manual cross-correlation of VMs, DataVolumes, PVCs, and PVs
- **Scale issues**: For large deployments (40,000 VMs = 80,000+ PVCs), manual tracking is unmanageable
- **Data loss risk**: No safeguards or visualization tools to prevent mistakes
- **Leftover resources**: No easy way to identify orphaned storage after migration
- **No relationship visualization**: Unlike `kubectl tree`, there's no tool to show VM → DV → PVC → PV relationships

## Tools

### `vm-tree.py` - VM Storage Relationship Visualizer

A tool that visualizes the storage resource hierarchy for OpenShift Virtualization VMs.

**Features:**
- Shows complete resource chain: VM → DataVolume → PVC → PV
- Displays storage class, size, and reclaim policy
- Warns about dangerous reclaim policies
- Can show all VMs using a specific storage class
- **Detects orphaned storage resources** (DataVolumes, PVCs, PVs not owned by any VM)
- Works with both `oc` (OpenShift) and `kubectl` (vanilla Kubernetes)
- Colored output for better readability

**Usage:**

```bash
# Show storage tree for a specific VM
./vm-tree.py fedora-vm-with-storage --namespace default

# Show all VMs using a storage class (useful for migration planning)
./vm-tree.py --storage-class standard

# Find orphaned storage resources in default namespace
./vm-tree.py --find-orphans

# Find orphaned resources across all namespaces
./vm-tree.py --find-orphans --all-namespaces
```

**Example Output - VM Storage Tree:**

```
================================================================================
  VM Storage Tree: fedora-vm-with-storage (namespace: default)
================================================================================

VirtualMachine: fedora-vm-with-storage
├─ UID: 86aa276e-2765-4902-bf0f-774f44eeb067
├─ Status: Stopped
│
├─ DataVolumes: (1 found)
│  └─ DataVolume: fedora-dv-inline
      ├─ Phase: WaitForFirstConsumer
      ├─ Size: 5Gi
      ├─ StorageClass: standard
      │
      └─ PersistentVolumeClaim: fedora-dv-inline
         ├─ Status: Pending
         └─ PersistentVolume: (not yet bound)

================================================================================
```

**Example Output - Orphaned Resources:**

```
================================================================================
  Orphaned Storage Resources
  Namespace: default
================================================================================

Found 1 orphaned resource(s):

❌ Orphaned DataVolumes: 1
(Not owned by any VirtualMachine)

  • DataVolume: fedora-dv
    ├─ Namespace: default
    ├─ Size: 5Gi
    ├─ StorageClass: standard
    ├─ Phase: WaitForFirstConsumer
    └─ Created: 2026-02-10T18:48:10Z

================================================================================
⚠️  These resources are consuming storage but not used by any VM
⚠️  Consider cleaning up to reclaim storage
================================================================================
```

This directly addresses the scale issue (eg when cluster has 40,000 VMs), where orphaned resources become impossible to track manually. With this tool, wasted storage can be identified across the entire cluster.

### Roadmap
1. Enhance `vm-tree.py` with:
   - Storage migration planning mode
   - Bulk operations support
   - Label-based tracking improvements

2. Build storage migration operator
   - Automated storage class updates
   - Data migration orchestration
   - Verification and rollback
   - Cleanup validation


## Resources

- [OpenShift Virtualization 4.20 Docs](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html-single/virtualization/index)
- [KubeVirt User Guide](https://kubevirt.io/user-guide/)
- [CDI GitHub](https://github.com/kubevirt/containerized-data-importer)

## Contributing

This is a prototype repository. Feedback and improvements welcome!

## License

Prototype code - use at your own risk.

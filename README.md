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

**Usage:**

```bash
# Show storage tree for a specific VM
./vm-tree.py fedora-vm-with-storage --namespace default

# Show all VMs using a storage class (useful for migration planning)
./vm-tree.py --storage-class gp3-csi
```

**Example Output:**

```
================================================================================
  VM Storage Tree: fedora-vm-with-storage (namespace: default)
================================================================================

VirtualMachine: fedora-vm-with-storage
├─ UID: 9d5f86aa-90f3-4646-a0f2-835826a30a10
├─ Status: Stopped
│
├─ DataVolumes: (1 found)
│  └─ DataVolume: fedora-dv-inline
      ├─ Phase: Bound
      ├─ Size: 10Gi
      ├─ StorageClass: gp3-csi
      │
      └─ PersistentVolumeClaim: fedora-dv-inline
         ├─ Status: Bound
         │
         └─ PersistentVolume: pvc-0843c555-450f-448d-be70-9b8c02a082c6
            ├─ Size: 10Gi
            └─ ReclaimPolicy: Delete ⚠️  (Data will be deleted with PVC!)

================================================================================
```

### Roadmap
1. Enhance `vm-tree.py` with:
   - Orphaned resource detection
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

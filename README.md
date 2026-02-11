# OpenShift Virtualization Storage Management Tools

Tools for managing VM storage relationships and automating storage class migrations at scale.

## Quick Start

```bash
# 1. Visualize VM storage relationships
./vm-tree.py fedora-vm-with-storage --namespace default

# 2. Find all VMs using a storage class
./vm-tree.py --storage-class standard

# 3. Detect orphaned storage resources
./vm-tree.py --find-orphans

# 4. Plan a storage class migration
./storage-migration.py plan --from-sc standard --to-sc standard-fast -n default

# 5. Execute the migration (dry-run first!)
./storage-migration.py execute --from-sc standard --to-sc standard-fast -n default --dry-run
```

## Motivation

OpenShift Virtualization's storage management has significant storage class migration challenges:

- **Manual storage migration**: Updating storage classes requires manual cross-correlation of VMs, DataVolumes, PVCs, and PVs
- **Scale issues**: For large deployments (40,000 VMs = 80,000+ PVCs), manual tracking is unmanageable
- **Data loss risk**: No safeguards or visualization tools to prevent mistakes
- **Leftover resources**: No easy way to identify orphaned storage after migration
- **No relationship visualization**: Unlike `kubectl tree`, there's no tool to show VM → DV → PVC → PV relationships, which makes it impossible to track relationships between all the resources in the cluster.
- **Time for lift** - Manually migration each VM takes ~30mins (with relationship tracking, workload backup, executing migration, cleaning up old resources etc). At scale, migrating 40,000+ VMs could end up taking 200+ hours. The plan for this tool is to bring the time down for that migration scenario to ~2 hours (1000x improvement!) - automatically plan the migration - execute - and monitor.

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

---

### `storage-migration.py` - Automated Storage Class Migration

A tool that automates the migration of VMs from one storage class to another, making storage migration at scale seameless.

**Features:**
- **Plan Mode**: Analyzes impact before migration (dry-run, shows all affected VMs)
- **Execute Mode**: Performs the actual migration with optional dry-run
- Finds all VMs using a specific storage class
- Calculates total storage to be migrated
- Creates new DataVolumes on target storage class
- Tracks migration with labels and timestamps
- Works with both `oc` (OpenShift) and `kubectl` (vanilla Kubernetes)

**The Value at Scale:**
- For **1 VM**: Manual migration takes ~30 minutes
- For **40,000 VMs**: Manual process = 20,000+ hours (impossible)
- **With this tool**: Plan once, execute in parallel, track automatically

**Usage:**

```bash
# Plan migration (shows what will be migrated)
./storage-migration.py plan --from-sc standard --to-sc standard-fast -n default

# Execute migration with dry-run first
./storage-migration.py execute --from-sc standard --to-sc standard-fast -n default --dry-run

# Execute actual migration
./storage-migration.py execute --from-sc standard --to-sc standard-fast -n default

# Plan migration across all namespaces
./storage-migration.py plan --from-sc gp2-csi --to-sc gp3-csi
```

**Example Output - Plan Mode:**

```
$ ./storage-migration.py plan --from-sc standard --to-sc standard-fast -n default
================================================================================
  STORAGE MIGRATION PLAN
================================================================================

  From StorageClass: standard
  To StorageClass:   standard-fast
  Namespace:         default

✅ Target storage class 'standard-fast' exists

Searching for VMs using storage class 'standard'...
Found 10 VM(s) to migrate:

1. VM: test-vm-001 (namespace: default)
   ├─ Status: Stopped
   ├─ DataVolumes to migrate: 1
   └─ DataVolume: test-vm-001-disk
        ├─ Size: 3Gi
        └─ Current StorageClass: standard

2. VM: test-vm-002 (namespace: default)
   ├─ Status: Stopped
   ├─ DataVolumes to migrate: 1
   └─ DataVolume: test-vm-002-disk
        ├─ Size: 3Gi
        └─ Current StorageClass: standard
.
.
.
.

9. VM: test-vm-009 (namespace: default)
   ├─ Status: Stopped
   ├─ DataVolumes to migrate: 1
   └─ DataVolume: test-vm-009-disk
        ├─ Size: 6Gi
        └─ Current StorageClass: standard

10. VM: test-vm-010 (namespace: default)
   ├─ Status: Stopped
   ├─ DataVolumes to migrate: 1
   └─ DataVolume: test-vm-010-disk
        ├─ Size: 6Gi
        └─ Current StorageClass: standard

================================================================================
  MIGRATION SUMMARY
================================================================================
  VMs to migrate:        10
  DataVolumes to clone:  10
  Total storage:         ~52 Gi

  ⚠️  Migration will:
     1. Create new DataVolumes on 'standard-fast'
     2. Clone data from existing DataVolumes
     3. Update VMs to use new DataVolumes
     4. Mark old DataVolumes as orphaned

  ⚠️  Recommended steps:
     1. Stop all VMs before migration (prevents data corruption)
     2. Use --dry-run first to test
     3. Back up critical VMs
     4. Clean up orphaned resources after verification

================================================================================
```

**Example Output - Dry-Run Mode:**

```
$ ./storage-migration.py execute --from-sc standard --to-sc standard-fast -n default --dry-run
================================================================================
  EXECUTING STORAGE MIGRATION
  (DRY RUN MODE - No actual changes will be made)
================================================================================

Migrating 10 VM(s)...

[1/10] Migrating VM: test-vm-001
  Creating new DataVolume: test-vm-001-disk-migrated-1770822362
  [DRY RUN] Would create:

apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: test-vm-001-disk-migrated-1770822362
  namespace: default
  labels:
    storage-migration: "true"
    migration-timestamp: "2026-02-11T10:06:02.288228"
    source-sc: "standard"
    target-sc: "standard-fast"
spec:
  source:
    pvc:
      namespace: default
      name: test-vm-001-disk
  storage:
    storageClassName: standard-fast
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 3Gi

  Updating VM spec to use new DataVolumes...
  [DRY RUN] Would patch VM to use new DataVolumes

[2/10] Migrating VM: test-vm-002
  Creating new DataVolume: test-vm-002-disk-migrated-1770822362
  [DRY RUN] Would create:

apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: test-vm-002-disk-migrated-1770822362
  namespace: default
  labels:
    storage-migration: "true"
    migration-timestamp: "2026-02-11T10:06:02.288336"
    source-sc: "standard"
    target-sc: "standard-fast"
spec:
  source:
    pvc:
      namespace: default
      name: test-vm-002-disk
  storage:
    storageClassName: standard-fast
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 3Gi

  Updating VM spec to use new DataVolumes...
  [DRY RUN] Would patch VM to use new DataVolumes
.
.
.
[10/10] Migrating VM: test-vm-010
  Creating new DataVolume: test-vm-010-disk-migrated-1770822362
  [DRY RUN] Would create:

apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: test-vm-010-disk-migrated-1770822362
  namespace: default
  labels:
    storage-migration: "true"
    migration-timestamp: "2026-02-11T10:06:02.288560"
    source-sc: "standard"
    target-sc: "standard-fast"
spec:
  source:
    pvc:
      namespace: default
      name: test-vm-010-disk
  storage:
    storageClassName: standard-fast
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 6Gi

  Updating VM spec to use new DataVolumes...
  [DRY RUN] Would patch VM to use new DataVolumes

================================================================================
DRY RUN COMPLETE
Run without --dry-run to execute actual migration
================================================================================
```

After migration, use `./vm-tree.py --find-orphans` to identify old resources for cleanup.

---

### Roadmap 

1. Enhance `storage-migration.py`:
   - **Parallel execution**: Migrate N VMs concurrently (configurable)
   - **Rollback capability**: Revert if migration fails
   - Progress tracking and status reporting

3. Web UI:
   - Interactive relationship graphs
   - Migration planning dashboard
   - Real-time progress monitoring


## Resources

- [OpenShift Virtualization 4.20 Docs](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html-single/virtualization/index)
- [KubeVirt User Guide](https://kubevirt.io/user-guide/)
- [CDI GitHub](https://github.com/kubevirt/containerized-data-importer)

## Contributing

This is a prototype repository. Feedback and improvements welcome!

## License

Prototype code - use at your own risk.

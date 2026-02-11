# Mass Migration Demo

Demonstrates migrating 10 VMs from `standard` to `standard-fast` storage class.

## Step 1: Create 10 Test VMs

```bash
# Apply the test VMs
kubectl apply -f test-data/10-vms-for-migration.yaml

# Wait for DataVolumes to be created
sleep 5

# Verify VMs were created
kubectl get vm -n default
```

Expected output:
```
NAME          AGE   STATUS    READY
test-vm-001   10s   Stopped   False
test-vm-002   10s   Stopped   False
...
test-vm-010   10s   Stopped   False
```

## Step 2: Verify Current State with vm-tree.py

```bash
# Show all VMs using 'standard' storage class
./vm-tree.py --storage-class standard

# Check one VM's storage tree
./vm-tree.py test-vm-001 -n default

# Check for any orphans (should be clean)
./vm-tree.py --find-orphans
```

## Step 3: Plan the Migration

```bash
# See what will be migrated
./storage-migration.py plan --from-sc standard --to-sc standard-fast -n default
```

Expected output:
```
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

...

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
  Total storage:         ~53 Gi
```

## Step 4: Execute Migration (Dry-Run First)

```bash
# Dry-run to see what would be created
./storage-migration.py execute --from-sc standard --to-sc standard-fast -n default --dry-run
```

## Step 5: Execute Actual Migration

```bash
# Execute the migration
./storage-migration.py execute --from-sc standard --to-sc standard-fast -n default
```

## Step 6: Monitor Progress in Real-Time

Open a **second terminal** and run:

```bash
# Watch migration progress
./migration-watch.py -n default --to-sc standard-fast
```

Expected display:
```
================================================================================
  STORAGE MIGRATION PROGRESS
  Namespace: default
  Updated: 2026-02-10 14:30:45
================================================================================

  Summary:
    Total DataVolumes:    10
    ✅ Completed:         3 (30.0%)
    ⏳ In Progress:       5
    ⏸  Pending:          2
    ❌ Failed:           0

  Overall Progress: [============                            ] 30.0%

================================================================================

NAMESPACE    NAME                              PHASE              PROGRESS              AGE
--------------------------------------------------------------------------------------------
default      test-vm-001-disk-migrated-...     Succeeded          [===============] 100%  5m
default      test-vm-002-disk-migrated-...     Succeeded          [===============] 100%  5m
default      test-vm-003-disk-migrated-...     Succeeded          [===============] 100%  4m
default      test-vm-004-disk-migrated-...     CloneInProgress    [=======        ] 45%   4m
default      test-vm-005-disk-migrated-...     CloneInProgress    [====           ] 25%   3m
...
```

## Step 7: Verify Migration Results

After all DataVolumes show "Succeeded":

```bash
# Check all DataVolumes
kubectl get dv -n default

# Should see both old and new DataVolumes
# - test-vm-001-disk (old, standard)
# - test-vm-001-disk-migrated-... (new, standard-fast)
```

## Step 8: Find Orphaned Resources

```bash
# Find old DataVolumes that are now orphaned
./vm-tree.py --find-orphans -n default
```

Expected output:
```
Found 10 orphaned resource(s):

❌ Orphaned DataVolumes: 10
(Not owned by any VirtualMachine)

  • DataVolume: test-vm-001-disk
    ├─ Namespace: default
    ├─ Size: 3Gi
    ├─ StorageClass: standard
    ...

  • DataVolume: test-vm-010-disk
    ├─ Namespace: default
    ├─ Size: 6Gi
    ├─ StorageClass: standard
    ...
```

## Step 9: Clean Up Old Resources

```bash
# Delete old DataVolumes (this is what customers struggle with at scale!)
kubectl delete dv test-vm-001-disk test-vm-002-disk test-vm-003-disk \
                  test-vm-004-disk test-vm-005-disk test-vm-006-disk \
                  test-vm-007-disk test-vm-008-disk test-vm-009-disk \
                  test-vm-010-disk -n default

# Verify cleanup
./vm-tree.py --find-orphans
```

## Step 10: Verify VMs Now Use New Storage Class

```bash
# Check a few VMs
./vm-tree.py test-vm-001 -n default
./vm-tree.py test-vm-005 -n default

# Show all VMs using standard-fast
./vm-tree.py --storage-class standard-fast
```

Expected: All 10 VMs should now be using `standard-fast`


## Step 11: Cleanup (After Demo)

```bash
# Remove all test VMs
$ kubectl delete vm test-vm-001 test-vm-002 test-vm-003 test-vm-004 test-vm-005 \
                  test-vm-006 test-vm-007 test-vm-008 test-vm-009 test-vm-010 -n default

# Clean up any remaining DataVolumes
$ kubectl delete dv --all -n default

# Verify clean state
$ kubectl get vm,dv -n default
$ ./vm-tree.py --find-orphans
```




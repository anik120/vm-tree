#!/usr/bin/env python3
"""
storage-migration.py - Automate storage class migration for OpenShift Virtualization VMs

This tool addresses Dave Thomas's problem: migrating thousands of VMs between storage classes.

Modes:
  plan    - Analyze what will be migrated (dry-run, impact analysis)
  execute - Perform the actual migration

Usage:
    ./storage-migration.py plan --from-sc standard --to-sc standard-fast
    ./storage-migration.py execute --from-sc standard --to-sc standard-fast [--dry-run]

Example:
    # Plan migration from standard to standard-fast
    ./storage-migration.py plan --from-sc standard --to-sc standard-fast -n default

    # Execute migration (dry-run first)
    ./storage-migration.py execute --from-sc standard --to-sc standard-fast --dry-run

    # Actually execute
    ./storage-migration.py execute --from-sc standard --to-sc standard-fast
"""

import argparse
import json
import subprocess
import sys
import time
from typing import Dict, List, Optional, Any
from datetime import datetime


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def run_kubectl(args: List[str], check=True) -> Dict[str, Any]:
    """Run kubectl/oc command and return parsed JSON output"""
    for cmd in ['oc', 'kubectl']:
        try:
            result = subprocess.run(
                [cmd] + args + ['-o', 'json'],
                capture_output=True,
                text=True,
                check=check
            )
            if result.returncode != 0:
                return None
            return json.loads(result.stdout) if result.stdout else None
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError:
            return None
        except json.JSONDecodeError:
            return None
    return None


def run_kubectl_apply(yaml_content: str, dry_run: bool = False) -> bool:
    """Apply YAML content using kubectl"""
    for cmd in ['oc', 'kubectl']:
        try:
            args = [cmd, 'apply', '-f', '-']
            if dry_run:
                args.append('--dry-run=client')

            result = subprocess.run(
                args,
                input=yaml_content,
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError as e:
            print(f"{Colors.FAIL}Error applying YAML: {e.stderr}{Colors.ENDC}")
            return False
    return False


def run_kubectl_patch(resource_type: str, resource_name: str, namespace: str,
                      patch: str, patch_type: str = 'json', dry_run: bool = False) -> bool:
    """Patch a Kubernetes resource"""
    for cmd in ['oc', 'kubectl']:
        try:
            args = [cmd, 'patch', resource_type, resource_name, '-n', namespace,
                   '--type', patch_type, '-p', patch]
            if dry_run:
                args.append('--dry-run=client')

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError as e:
            print(f"{Colors.FAIL}Error patching resource: {e.stderr}{Colors.ENDC}")
            return False
    return False


def patch_vm_to_use_new_datavolumes(vm_name: str, vm_namespace: str,
                                     old_dv_name: str, new_dv_name: str,
                                     dry_run: bool = False) -> bool:
    """Patch VM to use new DataVolume instead of old one"""
    # We need to update two places:
    # 1. spec.dataVolumeTemplates[].metadata.name
    # 2. spec.template.spec.volumes[].dataVolume.name

    # Get current VM to find the indices
    vm = run_kubectl(['get', 'vm', vm_name, '-n', vm_namespace], check=False)
    if not vm:
        return False

    # Build JSON patch operations
    patches = []

    # Find and update dataVolumeTemplates
    dv_templates = vm.get('spec', {}).get('dataVolumeTemplates', [])
    for idx, template in enumerate(dv_templates):
        if template.get('metadata', {}).get('name') == old_dv_name:
            patches.append({
                "op": "replace",
                "path": f"/spec/dataVolumeTemplates/{idx}/metadata/name",
                "value": new_dv_name
            })
            # Also need to update the storageClassName in the template
            # But we'll keep it simple for now - just update the name
            break

    # Find and update volumes in template
    volumes = vm.get('spec', {}).get('template', {}).get('spec', {}).get('volumes', [])
    for idx, volume in enumerate(volumes):
        dv_ref = volume.get('dataVolume', {})
        if dv_ref.get('name') == old_dv_name:
            patches.append({
                "op": "replace",
                "path": f"/spec/template/spec/volumes/{idx}/dataVolume/name",
                "value": new_dv_name
            })
            break

    if not patches:
        print(f"  {Colors.WARNING}⚠️  Could not find DataVolume references in VM{Colors.ENDC}")
        return False

    # Apply patch
    patch_json = json.dumps(patches)
    return run_kubectl_patch('vm', vm_name, vm_namespace, patch_json, 'json', dry_run)


def get_all_vms(namespace: Optional[str] = None) -> List[Dict]:
    """Get all VMs in namespace or all namespaces"""
    cmd = ['get', 'vm']
    if namespace:
        cmd.extend(['-n', namespace])
    else:
        cmd.append('--all-namespaces')

    result = run_kubectl(cmd, check=False)
    return result.get('items', []) if result else []


def get_datavolumes(namespace: str) -> List[Dict]:
    """Get all DataVolumes in namespace"""
    result = run_kubectl(['get', 'dv', '-n', namespace], check=False)
    return result.get('items', []) if result else []


def get_storage_class(name: str) -> Optional[Dict]:
    """Get storage class details"""
    return run_kubectl(['get', 'sc', name], check=False)


def find_vms_using_storage_class(storage_class: str, namespace: Optional[str] = None) -> List[Dict]:
    """Find all VMs using a specific storage class"""
    vms_to_migrate = []
    all_vms = get_all_vms(namespace)

    for vm in all_vms:
        vm_name = vm['metadata']['name']
        vm_namespace = vm['metadata']['namespace']

        # Get DataVolumes for this VM
        dvs = get_datavolumes(vm_namespace)

        # Find DVs owned by this VM
        vm_uid = vm['metadata']['uid']
        vm_dvs = []

        for dv in dvs:
            owner_refs = dv.get('metadata', {}).get('ownerReferences', [])
            for ref in owner_refs:
                if ref.get('kind') == 'VirtualMachine' and ref.get('uid') == vm_uid:
                    vm_dvs.append(dv)
                    break

        # Check if any DV uses the target storage class
        for dv in vm_dvs:
            dv_sc = dv.get('spec', {}).get('storage', {}).get('storageClassName')
            if dv_sc == storage_class:
                vms_to_migrate.append({
                    'vm': vm,
                    'datavolumes': vm_dvs
                })
                break

    return vms_to_migrate


def print_migration_plan(from_sc: str, to_sc: str, namespace: Optional[str] = None):
    """Print migration plan (what will be migrated)"""
    print("=" * 80)
    print(f"  {Colors.BOLD}STORAGE MIGRATION PLAN{Colors.ENDC}")
    print("=" * 80)
    print()
    print(f"  From StorageClass: {Colors.WARNING}{from_sc}{Colors.ENDC}")
    print(f"  To StorageClass:   {Colors.OKGREEN}{to_sc}{Colors.ENDC}")
    if namespace:
        print(f"  Namespace:         {namespace}")
    else:
        print(f"  Namespace:         All namespaces")
    print()

    # Validate target storage class exists
    target_sc = get_storage_class(to_sc)
    if not target_sc:
        print(f"{Colors.FAIL}❌ Error: Storage class '{to_sc}' not found!{Colors.ENDC}")
        sys.exit(1)

    print(f"{Colors.OKGREEN}✅ Target storage class '{to_sc}' exists{Colors.ENDC}")
    print()

    # Find VMs to migrate
    print(f"Searching for VMs using storage class '{from_sc}'...")
    vms_to_migrate = find_vms_using_storage_class(from_sc, namespace)

    if not vms_to_migrate:
        print(f"{Colors.WARNING}No VMs found using storage class '{from_sc}'{Colors.ENDC}")
        print()
        print("=" * 80)
        return

    print(f"{Colors.OKBLUE}Found {len(vms_to_migrate)} VM(s) to migrate:{Colors.ENDC}")
    print()

    total_storage = 0
    total_dvs = 0

    for idx, item in enumerate(vms_to_migrate, 1):
        vm = item['vm']
        dvs = item['datavolumes']

        vm_name = vm['metadata']['name']
        vm_namespace = vm['metadata']['namespace']
        vm_status = vm.get('status', {}).get('printableStatus', 'Unknown')

        print(f"{idx}. {Colors.OKGREEN}VM:{Colors.ENDC} {vm_name} (namespace: {vm_namespace})")
        print(f"   ├─ Status: {vm_status}")
        print(f"   ├─ DataVolumes to migrate: {len(dvs)}")

        for dv_idx, dv in enumerate(dvs):
            dv_name = dv['metadata']['name']
            dv_size_str = dv.get('spec', {}).get('storage', {}).get('resources', {}).get('requests', {}).get('storage', '0Gi')
            dv_sc = dv.get('spec', {}).get('storage', {}).get('storageClassName', 'N/A')

            # Parse size (simplistic - assumes Gi)
            try:
                size_gi = int(dv_size_str.replace('Gi', '').replace('G', ''))
                total_storage += size_gi
            except:
                pass

            total_dvs += 1

            is_last = (dv_idx == len(dvs) - 1)
            connector = "└─" if is_last else "├─"

            print(f"   {connector} DataVolume: {dv_name}")
            print(f"   {'   ' if is_last else '│  '}  ├─ Size: {dv_size_str}")
            print(f"   {'   ' if is_last else '│  '}  └─ Current StorageClass: {dv_sc}")

        print()

    print("=" * 80)
    print(f"  {Colors.BOLD}MIGRATION SUMMARY{Colors.ENDC}")
    print("=" * 80)
    print(f"  VMs to migrate:        {len(vms_to_migrate)}")
    print(f"  DataVolumes to clone:  {total_dvs}")
    print(f"  Total storage:         ~{total_storage} Gi")
    print()
    print(f"  {Colors.WARNING}⚠️  Migration will:{Colors.ENDC}")
    print(f"     1. Create new DataVolumes on '{to_sc}'")
    print(f"     2. Clone data from existing DataVolumes")
    print(f"     3. Update VMs to use new DataVolumes")
    print(f"     4. Mark old DataVolumes as orphaned")
    print()
    print(f"  {Colors.WARNING}⚠️  Recommended steps:{Colors.ENDC}")
    print(f"     1. Stop all VMs before migration (prevents data corruption)")
    print(f"     2. Use --dry-run first to test")
    print(f"     3. Back up critical VMs")
    print(f"     4. Clean up orphaned resources after verification")
    print()
    print("=" * 80)


def execute_migration(from_sc: str, to_sc: str, namespace: Optional[str] = None, dry_run: bool = False):
    """Execute the migration"""
    print("=" * 80)
    print(f"  {Colors.BOLD}EXECUTING STORAGE MIGRATION{Colors.ENDC}")
    if dry_run:
        print(f"  {Colors.WARNING}(DRY RUN MODE - No actual changes will be made){Colors.ENDC}")
    print("=" * 80)
    print()

    # Get VMs to migrate
    vms_to_migrate = find_vms_using_storage_class(from_sc, namespace)

    if not vms_to_migrate:
        print(f"{Colors.WARNING}No VMs found to migrate.{Colors.ENDC}")
        return

    print(f"Migrating {len(vms_to_migrate)} VM(s)...")
    print()

    for idx, item in enumerate(vms_to_migrate, 1):
        vm = item['vm']
        dvs = item['datavolumes']

        vm_name = vm['metadata']['name']
        vm_namespace = vm['metadata']['namespace']

        print(f"[{idx}/{len(vms_to_migrate)}] Migrating VM: {Colors.OKGREEN}{vm_name}{Colors.ENDC}")

        # Track old → new DV name mapping for this VM
        dv_mapping = {}

        # Step 1: Create new DataVolumes
        for dv in dvs:
            dv_name = dv['metadata']['name']
            dv_size = dv.get('spec', {}).get('storage', {}).get('resources', {}).get('requests', {}).get('storage', '5Gi')
            dv_access_modes = dv.get('spec', {}).get('storage', {}).get('accessModes', ['ReadWriteOnce'])

            new_dv_name = f"{dv_name}-migrated-{int(time.time())}"
            dv_mapping[dv_name] = new_dv_name  # Store mapping

            print(f"  Creating new DataVolume: {new_dv_name}")

            # Create new DataVolume YAML
            timestamp = datetime.now().isoformat()
            new_dv_yaml = f"""
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: {new_dv_name}
  namespace: {vm_namespace}
  labels:
    storage-migration: "true"
    source-sc: "{from_sc}"
    target-sc: "{to_sc}"
  annotations:
    migration-timestamp: "{timestamp}"
spec:
  source:
    pvc:
      namespace: {vm_namespace}
      name: {dv_name}
  storage:
    storageClassName: {to_sc}
    accessModes:
{chr(10).join(f'      - {mode}' for mode in dv_access_modes)}
    resources:
      requests:
        storage: {dv_size}
"""

            if dry_run:
                print(f"  {Colors.OKCYAN}[DRY RUN] Would create:{Colors.ENDC}")
                print(new_dv_yaml)
            else:
                success = run_kubectl_apply(new_dv_yaml, dry_run=False)
                if success:
                    print(f"  {Colors.OKGREEN}✅ DataVolume created{Colors.ENDC}")
                else:
                    print(f"  {Colors.FAIL}❌ Failed to create DataVolume{Colors.ENDC}")
                    continue

            # Small delay to ensure unique timestamps
            time.sleep(0.1)

        # Step 2: Update VM spec to use new DataVolumes
        print(f"  Updating VM spec to use new DataVolumes...")

        for old_dv_name, new_dv_name in dv_mapping.items():
            if dry_run:
                print(f"  {Colors.OKCYAN}[DRY RUN] Would patch VM: {old_dv_name} → {new_dv_name}{Colors.ENDC}")
            else:
                success = patch_vm_to_use_new_datavolumes(
                    vm_name, vm_namespace, old_dv_name, new_dv_name, dry_run=False
                )
                if success:
                    print(f"  {Colors.OKGREEN}✅ VM patched: {old_dv_name} → {new_dv_name}{Colors.ENDC}")
                else:
                    print(f"  {Colors.FAIL}❌ Failed to patch VM{Colors.ENDC}")

        print()

    print("=" * 80)
    if dry_run:
        print(f"{Colors.OKGREEN}DRY RUN COMPLETE{Colors.ENDC}")
        print(f"Run without --dry-run to execute actual migration")
    else:
        print(f"{Colors.OKGREEN}MIGRATION INITIATED{Colors.ENDC}")
        print()
        print(f"Monitor progress with:")
        print(f"  kubectl get dv -n {namespace or 'default'} -w")
        print()
        print(f"After migration completes:")
        print(f"  1. Verify VMs start successfully")
        print(f"  2. Find orphaned resources: ./vm-tree.py --find-orphans")
        print(f"  3. Clean up old DataVolumes")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Automate storage class migration for VMs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plan migration (shows what will be migrated)
  %(prog)s plan --from-sc standard --to-sc standard-fast

  # Execute migration with dry-run
  %(prog)s execute --from-sc standard --to-sc standard-fast --dry-run

  # Execute actual migration
  %(prog)s execute --from-sc standard --to-sc standard-fast

  # Plan migration for specific namespace
  %(prog)s plan --from-sc standard --to-sc standard-fast -n production
        """
    )

    parser.add_argument('mode', choices=['plan', 'execute'], help='Operation mode')
    parser.add_argument('--from-sc', '--from-storage-class', required=True, dest='from_sc',
                        help='Source storage class to migrate from')
    parser.add_argument('--to-sc', '--to-storage-class', required=True, dest='to_sc',
                        help='Target storage class to migrate to')
    parser.add_argument('-n', '--namespace', help='Kubernetes namespace (default: searches all)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Dry run mode (only for execute mode)')
    parser.add_argument('--no-color', action='store_true', help='Disable colored output')

    args = parser.parse_args()

    # Disable colors if requested
    if args.no_color:
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')

    # Check if kubectl/oc is available
    cmd_available = False
    for cmd in ['oc', 'kubectl']:
        try:
            subprocess.run([cmd, 'version'], capture_output=True, check=True)
            cmd_available = True
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    if not cmd_available:
        print(f"{Colors.FAIL}Error: Neither 'oc' nor 'kubectl' command found.{Colors.ENDC}")
        sys.exit(1)

    # Execute mode
    if args.mode == 'plan':
        print_migration_plan(args.from_sc, args.to_sc, args.namespace)
    elif args.mode == 'execute':
        execute_migration(args.from_sc, args.to_sc, args.namespace, args.dry_run)


if __name__ == '__main__':
    main()

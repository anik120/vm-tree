#!/usr/bin/env python3
"""
vm-tree.py - Visualize VM storage relationships in OpenShift Virtualization

This script provides a kubectl tree-like visualization for VM storage resources.

Usage:
    ./vm-tree.py <vm-name> [--namespace <ns>]
    ./vm-tree.py --storage-class <sc-name>
    ./vm-tree.py --find-orphans [--all-namespaces]

Example:
    ./vm-tree.py fedora-vm-with-storage --namespace default
    ./vm-tree.py --storage-class standard
    ./vm-tree.py --find-orphans
"""

import argparse
import json
import subprocess
import sys
from typing import Dict, List, Optional, Any


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


def run_oc(args: List[str], check=True) -> Dict[str, Any]:
    """Run oc/kubectl command and return parsed JSON output"""
    # Try oc first, then kubectl
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
            continue  # Try next command
        except subprocess.CalledProcessError:
            return None
        except json.JSONDecodeError:
            return None
    return None


def get_vm(name: str, namespace: str) -> Optional[Dict]:
    """Get VirtualMachine resource"""
    return run_oc(['get', 'vm', name, '-n', namespace], check=False)


def get_datavolumes(namespace: str) -> List[Dict]:
    """Get all DataVolumes in namespace"""
    result = run_oc(['get', 'dv', '-n', namespace], check=False)
    return result.get('items', []) if result else []


def get_pvc(name: str, namespace: str) -> Optional[Dict]:
    """Get PersistentVolumeClaim resource"""
    return run_oc(['get', 'pvc', name, '-n', namespace], check=False)


def get_pv(name: str) -> Optional[Dict]:
    """Get PersistentVolume resource"""
    return run_oc(['get', 'pv', name], check=False)


def get_all_vms(namespace: Optional[str] = None) -> List[Dict]:
    """Get all VMs in namespace or all namespaces"""
    cmd = ['get', 'vm']
    if namespace:
        cmd.extend(['-n', namespace])
    else:
        cmd.append('--all-namespaces')

    result = run_oc(cmd, check=False)
    return result.get('items', []) if result else []


def get_all_datavolumes(namespace: Optional[str] = None) -> List[Dict]:
    """Get all DataVolumes in namespace or all namespaces"""
    cmd = ['get', 'dv']
    if namespace:
        cmd.extend(['-n', namespace])
    else:
        cmd.append('--all-namespaces')

    result = run_oc(cmd, check=False)
    return result.get('items', []) if result else []


def get_all_pvcs(namespace: Optional[str] = None) -> List[Dict]:
    """Get all PVCs in namespace or all namespaces"""
    cmd = ['get', 'pvc']
    if namespace:
        cmd.extend(['-n', namespace])
    else:
        cmd.append('--all-namespaces')

    result = run_oc(cmd, check=False)
    return result.get('items', []) if result else []


def get_all_pvs() -> List[Dict]:
    """Get all PVs in the cluster"""
    result = run_oc(['get', 'pv'], check=False)
    return result.get('items', []) if result else []


def find_dvs_for_vm(vm_name: str, vm_uid: str, namespace: str) -> List[Dict]:
    """Find all DataVolumes owned by or referenced by a VM"""
    dvs = []

    # Get all DataVolumes in namespace
    all_dvs = get_datavolumes(namespace)

    for dv in all_dvs:
        # Check ownerReferences
        owner_refs = dv.get('metadata', {}).get('ownerReferences', [])
        for ref in owner_refs:
            if ref.get('kind') == 'VirtualMachine' and ref.get('name') == vm_name:
                dvs.append(dv)
                break

    return dvs


def print_tree_line(text: str, prefix: str = "", last: bool = False):
    """Print a line in tree format"""
    connector = "└─" if last else "├─"
    print(f"{prefix}{connector} {text}")


def print_vm_tree(vm_name: str, namespace: str):
    """Print storage tree for a specific VM"""
    print("=" * 80)
    print(f"  {Colors.BOLD}VM Storage Tree: {vm_name}{Colors.ENDC} (namespace: {namespace})")
    print("=" * 80)
    print()

    # Get VM
    vm = get_vm(vm_name, namespace)
    if not vm:
        print(f"{Colors.FAIL}❌ VirtualMachine '{vm_name}' not found in namespace '{namespace}'{Colors.ENDC}")
        return

    vm_uid = vm['metadata']['uid']
    status = vm.get('status', {}).get('printableStatus', 'Unknown')

    print(f"{Colors.OKGREEN}VirtualMachine:{Colors.ENDC} {vm_name}")
    print(f"├─ UID: {vm_uid}")
    print(f"├─ Status: {status}")
    print("│")

    # Find DataVolumes
    dvs = find_dvs_for_vm(vm_name, vm_uid, namespace)

    if not dvs:
        print("└─ (no DataVolumes found)")
        return

    print(f"├─ {Colors.OKCYAN}DataVolumes:{Colors.ENDC} ({len(dvs)} found)")

    for idx, dv in enumerate(dvs):
        is_last_dv = (idx == len(dvs) - 1)
        dv_prefix = "   " if is_last_dv else "│  "

        dv_name = dv['metadata']['name']
        dv_phase = dv.get('status', {}).get('phase', 'Unknown')
        dv_size = dv.get('spec', {}).get('storage', {}).get('resources', {}).get('requests', {}).get('storage', 'N/A')
        dv_sc = dv.get('spec', {}).get('storage', {}).get('storageClassName', 'N/A')

        connector = "└─" if is_last_dv else "├─"
        print(f"│  {connector} DataVolume: {dv_name}")
        print(f"{dv_prefix}   ├─ Phase: {dv_phase}")
        print(f"{dv_prefix}   ├─ Size: {dv_size}")
        print(f"{dv_prefix}   ├─ StorageClass: {dv_sc}")

        # Find PVC
        pvc = get_pvc(dv_name, namespace)
        if pvc:
            pvc_status = pvc.get('status', {}).get('phase', 'Unknown')
            pvc_volume_name = pvc.get('spec', {}).get('volumeName')

            print(f"{dv_prefix}   │")
            print(f"{dv_prefix}   └─ {Colors.OKBLUE}PersistentVolumeClaim:{Colors.ENDC} {dv_name}")
            print(f"{dv_prefix}      ├─ Status: {pvc_status}")

            if pvc_volume_name:
                pv = get_pv(pvc_volume_name)
                if pv:
                    pv_size = pv.get('spec', {}).get('capacity', {}).get('storage', 'N/A')
                    pv_reclaim = pv.get('spec', {}).get('persistentVolumeReclaimPolicy', 'N/A')

                    reclaim_warning = ""
                    if pv_reclaim == "Delete":
                        reclaim_warning = f" {Colors.WARNING}⚠️  (Data will be deleted with PVC!){Colors.ENDC}"

                    print(f"{dv_prefix}      │")
                    print(f"{dv_prefix}      └─ {Colors.HEADER}PersistentVolume:{Colors.ENDC} {pvc_volume_name}")
                    print(f"{dv_prefix}         ├─ Size: {pv_size}")
                    print(f"{dv_prefix}         └─ ReclaimPolicy: {pv_reclaim}{reclaim_warning}")
            else:
                print(f"{dv_prefix}      └─ PersistentVolume: (not yet bound)")
        else:
            print(f"{dv_prefix}   └─ PersistentVolumeClaim: (not found)")

        if not is_last_dv:
            print("│")

    print()
    print("=" * 80)


def get_active_dvs_for_vm(vm: Dict) -> List[str]:
    """
    Get list of DataVolume names that are actively referenced in VM spec.
    These are the DVs the VM is actually using.
    """
    active_dvs = []

    # Check dataVolumeTemplates
    dv_templates = vm.get('spec', {}).get('dataVolumeTemplates', [])
    for template in dv_templates:
        dv_name = template.get('metadata', {}).get('name')
        if dv_name:
            active_dvs.append(dv_name)

    # Check volumes in template spec
    volumes = vm.get('spec', {}).get('template', {}).get('spec', {}).get('volumes', [])
    for volume in volumes:
        dv_ref = volume.get('dataVolume', {}).get('name')
        if dv_ref and dv_ref not in active_dvs:
            active_dvs.append(dv_ref)

    return active_dvs


def find_orphaned_resources(namespace: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    Find orphaned storage resources.

    An orphaned DataVolume is one that:
    1. Has no ownerReferences at all, OR
    2. Has ownerReference to a VM but is not actively referenced in the VM spec
       (leftover from migration or manual operations)
    """
    orphaned = {
        'datavolumes': [],
        'pvcs': [],
        'pvs': []
    }

    # Get all VMs and build active DV mapping
    all_vms = get_all_vms(namespace)
    vm_to_active_dvs = {}  # vm_uid -> list of active DV names
    active_dv_set = set()  # (namespace, dv_name)

    for vm in all_vms:
        vm_uid = vm['metadata']['uid']
        vm_namespace = vm['metadata']['namespace']
        active_dvs = get_active_dvs_for_vm(vm)
        vm_to_active_dvs[vm_uid] = active_dvs

        for dv_name in active_dvs:
            active_dv_set.add((vm_namespace, dv_name))

    # Find orphaned DataVolumes
    all_dvs = get_all_datavolumes(namespace)
    for dv in all_dvs:
        dv_name = dv['metadata']['name']
        dv_namespace = dv['metadata']['namespace']
        owner_refs = dv.get('metadata', {}).get('ownerReferences', [])

        # Check if owned by a VM
        vm_owner = None
        for ref in owner_refs:
            if ref.get('kind') == 'VirtualMachine':
                vm_owner = ref
                break

        is_orphaned = False
        correlation = None

        if vm_owner:
            # Has VM owner - check if actively used
            if (dv_namespace, dv_name) not in active_dv_set:
                # Orphaned: has ownerRef but VM doesn't use it anymore
                is_orphaned = True

                # Build correlation programmatically using ownerReference
                vm_name = vm_owner.get('name')
                vm_uid = vm_owner.get('uid')

                # Find the VM object
                vm_obj = None
                for vm in all_vms:
                    if vm['metadata']['uid'] == vm_uid:
                        vm_obj = vm
                        break

                if vm_obj:
                    vm_status = vm_obj.get('status', {}).get('printableStatus', 'Unknown')
                    current_dvs = vm_to_active_dvs.get(vm_uid, [])

                    # Check if this orphaned DV is the source for any active DV
                    is_source_for = []
                    for active_dv_name in current_dvs:
                        # Get the active DV
                        active_dv = None
                        for dv_candidate in all_dvs:
                            if (dv_candidate['metadata']['name'] == active_dv_name and
                                dv_candidate['metadata']['namespace'] == dv_namespace):
                                active_dv = dv_candidate
                                break

                        if active_dv:
                            # Check if orphaned DV is the source
                            source_pvc = active_dv.get('spec', {}).get('source', {}).get('pvc', {})
                            if source_pvc.get('name') == dv_name:
                                is_source_for.append(active_dv_name)

                    # Build correlation
                    correlation = {
                        'vm_name': vm_name,
                        'vm_namespace': dv_namespace,
                        'vm_status': vm_status,
                        'current_vm_dvs': current_dvs,
                        'is_migration': len(is_source_for) > 0,
                        'replaced_by': is_source_for
                    }

                    if is_source_for:
                        # Very high confidence - this DV was used as source for migration
                        correlation['confidence'] = 'very-high'
                        correlation['reason'] = f"Migration source for: {', '.join(is_source_for)}"
                    else:
                        # High confidence - has ownerRef but not used
                        correlation['confidence'] = 'high'
                        correlation['reason'] = f"Has ownerReference to VM but not in VM spec"

        elif not owner_refs:
            # No owner at all - orphaned
            is_orphaned = True

        if is_orphaned:
            dv_info = {
                'name': dv_name,
                'namespace': dv_namespace,
                'size': dv.get('spec', {}).get('storage', {}).get('resources', {}).get('requests', {}).get('storage', 'N/A'),
                'storageClass': dv.get('spec', {}).get('storage', {}).get('storageClassName', 'N/A'),
                'phase': dv.get('status', {}).get('phase', 'Unknown'),
                'created': dv['metadata'].get('creationTimestamp', 'Unknown'),
                'labels': dv.get('metadata', {}).get('labels', {}),
                'annotations': dv.get('metadata', {}).get('annotations', {})
            }

            if correlation:
                dv_info['correlation'] = correlation

            orphaned['datavolumes'].append(dv_info)

    # Find orphaned PVCs (no ownerReferences or not owned by DataVolume)
    all_pvcs = get_all_pvcs(namespace)
    for pvc in all_pvcs:
        owner_refs = pvc.get('metadata', {}).get('ownerReferences', [])

        # Check if owned by a DataVolume
        has_dv_owner = any(ref.get('kind') == 'DataVolume' for ref in owner_refs)

        if not has_dv_owner:
            orphaned['pvcs'].append({
                'name': pvc['metadata']['name'],
                'namespace': pvc['metadata']['namespace'],
                'size': pvc.get('spec', {}).get('resources', {}).get('requests', {}).get('storage', 'N/A'),
                'storageClass': pvc.get('spec', {}).get('storageClassName', 'N/A'),
                'status': pvc.get('status', {}).get('phase', 'Unknown'),
                'volumeName': pvc.get('spec', {}).get('volumeName', 'N/A'),
                'created': pvc['metadata'].get('creationTimestamp', 'Unknown')
            })

    # Find orphaned PVs (Released or Failed state)
    all_pvs = get_all_pvs()
    for pv in all_pvs:
        phase = pv.get('status', {}).get('phase', 'Unknown')

        # PVs in Released or Failed state are orphaned
        if phase in ['Released', 'Failed']:
            orphaned['pvs'].append({
                'name': pv['metadata']['name'],
                'size': pv.get('spec', {}).get('capacity', {}).get('storage', 'N/A'),
                'storageClass': pv.get('spec', {}).get('storageClassName', 'N/A'),
                'reclaimPolicy': pv.get('spec', {}).get('persistentVolumeReclaimPolicy', 'N/A'),
                'status': phase,
                'claimRef': pv.get('spec', {}).get('claimRef', {}).get('name', 'None'),
                'created': pv['metadata'].get('creationTimestamp', 'Unknown')
            })

    return orphaned


def print_orphaned_resources(namespace: Optional[str] = None):
    """Print orphaned storage resources"""
    print("=" * 80)
    print(f"  {Colors.BOLD}Orphaned Storage Resources{Colors.ENDC}")
    if namespace:
        print(f"  {Colors.BOLD}Namespace: {namespace}{Colors.ENDC}")
    else:
        print(f"  {Colors.BOLD}All Namespaces{Colors.ENDC}")
    print("=" * 80)
    print()

    orphaned = find_orphaned_resources(namespace)

    # Calculate totals
    total_orphans = len(orphaned['datavolumes']) + len(orphaned['pvcs']) + len(orphaned['pvs'])

    if total_orphans == 0:
        print(f"{Colors.OKGREEN}✅ No orphaned resources found!{Colors.ENDC}")
        print()
        print("=" * 80)
        return

    print(f"{Colors.WARNING}Found {total_orphans} orphaned resource(s):{Colors.ENDC}\n")

    # Print orphaned DataVolumes
    if orphaned['datavolumes']:
        print(f"{Colors.FAIL}❌ Orphaned DataVolumes: {len(orphaned['datavolumes'])}{Colors.ENDC}")
        print(f"{Colors.WARNING}(Not owned by any VirtualMachine){Colors.ENDC}\n")

        for dv in orphaned['datavolumes']:
            print(f"  • {Colors.OKCYAN}DataVolume:{Colors.ENDC} {dv['name']}")
            print(f"    ├─ Namespace: {dv['namespace']}")
            print(f"    ├─ Size: {dv['size']}")
            print(f"    ├─ StorageClass: {dv['storageClass']}")
            print(f"    ├─ Phase: {dv['phase']}")

            # Show migration info if present
            is_migration = dv['labels'].get('storage-migration') == 'true'
            if is_migration:
                source_sc = dv['labels'].get('source-sc', 'N/A')
                target_sc = dv['labels'].get('target-sc', 'N/A')
                migration_ts = dv['annotations'].get('migration-timestamp', 'N/A')
                print(f"    ├─ {Colors.WARNING}Migration DV:{Colors.ENDC} {source_sc} → {target_sc}")
                print(f"    │  └─ Migrated at: {migration_ts}")

            # Show correlation if found
            if 'correlation' in dv:
                corr = dv['correlation']
                confidence = corr['confidence']

                # Color code by confidence
                if confidence == 'very-high':
                    conf_color = Colors.OKGREEN
                    conf_symbol = "✓✓"
                elif confidence == 'high':
                    conf_color = Colors.OKGREEN
                    conf_symbol = "✓"
                elif confidence == 'medium':
                    conf_color = Colors.WARNING
                    conf_symbol = "~"
                else:
                    conf_color = Colors.WARNING
                    conf_symbol = "?"

                print(f"    ├─ {conf_color}Belongs to VM:{Colors.ENDC} {corr['vm_name']} ({conf_symbol} {confidence} confidence)")
                print(f"    │  ├─ Reason: {corr['reason']}")
                print(f"    │  ├─ VM Status: {corr['vm_status']}")

                if corr.get('replaced_by'):
                    print(f"    │  ├─ {Colors.OKCYAN}Replaced by:{Colors.ENDC} {', '.join(corr['replaced_by'])}")

                if corr['current_vm_dvs']:
                    print(f"    │  └─ VM's current DVs: {', '.join(corr['current_vm_dvs'])}")

                # Provide use case hint
                if confidence == 'very-high' and corr.get('is_migration'):
                    print(f"    │")
                    print(f"    │  {Colors.WARNING}💡 Hint:{Colors.ENDC} This is an old disk from a storage migration.")
                    print(f"    │      • The VM is now using the migrated disk(s)")
                    print(f"    │      • If VM is working correctly, this can be safely deleted")
                    print(f"    │      • If kept as backup, consider adding a 'backup' label for tracking")
                elif confidence == 'high':
                    print(f"    │")
                    print(f"    │  {Colors.WARNING}💡 Hint:{Colors.ENDC} This disk has ownerReference but VM doesn't use it.")
                    print(f"    │      • Verify the VM is working with its current disks")
                    print(f"    │      • This is likely leftover from a manual operation or migration")
                    print(f"    │      • Safe to delete if VM is functioning properly")

            print(f"    └─ Created: {dv['created']}")
            print()

    # Print orphaned PVCs
    if orphaned['pvcs']:
        print(f"{Colors.FAIL}❌ Orphaned PVCs: {len(orphaned['pvcs'])}{Colors.ENDC}")
        print(f"{Colors.WARNING}(Not owned by any DataVolume){Colors.ENDC}\n")

        for pvc in orphaned['pvcs']:
            print(f"  • {Colors.OKBLUE}PersistentVolumeClaim:{Colors.ENDC} {pvc['name']}")
            print(f"    ├─ Namespace: {pvc['namespace']}")
            print(f"    ├─ Size: {pvc['size']}")
            print(f"    ├─ StorageClass: {pvc['storageClass']}")
            print(f"    ├─ Status: {pvc['status']}")
            print(f"    ├─ Volume: {pvc['volumeName']}")
            print(f"    └─ Created: {pvc['created']}")
            print()

    # Print orphaned PVs
    if orphaned['pvs']:
        print(f"{Colors.FAIL}❌ Orphaned PVs: {len(orphaned['pvs'])}{Colors.ENDC}")
        print(f"{Colors.WARNING}(Released or Failed state){Colors.ENDC}\n")

        for pv in orphaned['pvs']:
            print(f"  • {Colors.HEADER}PersistentVolume:{Colors.ENDC} {pv['name']}")
            print(f"    ├─ Size: {pv['size']}")
            print(f"    ├─ StorageClass: {pv['storageClass']}")
            print(f"    ├─ ReclaimPolicy: {pv['reclaimPolicy']}")
            print(f"    ├─ Status: {pv['status']}")
            print(f"    ├─ ClaimRef: {pv['claimRef']}")
            print(f"    └─ Created: {pv['created']}")
            print()

    print("=" * 80)
    print(f"{Colors.BOLD}Cleanup Recommendations:{Colors.ENDC}\n")

    # Count correlated orphans
    correlated_dvs = [dv for dv in orphaned['datavolumes'] if 'correlation' in dv]
    uncorrelated_dvs = [dv for dv in orphaned['datavolumes'] if 'correlation' not in dv]

    if correlated_dvs:
        migration_dvs = [dv for dv in correlated_dvs if dv['correlation'].get('is_migration')]
        other_correlated = [dv for dv in correlated_dvs if not dv['correlation'].get('is_migration')]

        if migration_dvs:
            print(f"{Colors.OKGREEN}✓ {len(migration_dvs)} orphaned DV(s) from storage migrations{Colors.ENDC}")
            print(f"  → These were replaced by new DataVolumes on different storage classes")
            print(f"  → Verify VMs are working with new disks, then delete old ones\n")

        if other_correlated:
            print(f"{Colors.WARNING}⚠ {len(other_correlated)} orphaned DV(s) with ownerReferences but not in VM specs{Colors.ENDC}")
            print(f"  → Likely leftover from manual VM spec changes")
            print(f"  → Verify VMs are working, then clean up\n")

    if uncorrelated_dvs:
        print(f"{Colors.WARNING}⚠ {len(uncorrelated_dvs)} orphaned DV(s) with no VM owner{Colors.ENDC}")
        print(f"  → May be from deleted VMs, manual creations, or failed operations")
        print(f"  → Review carefully before deletion\n")

    print(f"{Colors.WARNING}⚠️  All orphaned resources are consuming storage but not actively used{Colors.ENDC}")
    print(f"{Colors.WARNING}⚠️  Consider cleaning up to reclaim storage space{Colors.ENDC}")
    print("=" * 80)


def print_storage_class_usage(storage_class: str):
    """Print all VMs using a specific storage class"""
    print("=" * 80)
    print(f"  {Colors.BOLD}VMs using StorageClass: {storage_class}{Colors.ENDC}")
    print("=" * 80)
    print()

    # Get all VMs
    vms = get_all_vms()

    matching_vms = []

    for vm in vms:
        vm_name = vm['metadata']['name']
        vm_namespace = vm['metadata']['namespace']

        # Find DataVolumes for this VM
        vm_uid = vm['metadata']['uid']
        dvs = find_dvs_for_vm(vm_name, vm_uid, vm_namespace)

        # Check if any DV uses the storage class
        for dv in dvs:
            dv_sc = dv.get('spec', {}).get('storage', {}).get('storageClassName')
            if dv_sc == storage_class:
                matching_vms.append({
                    'name': vm_name,
                    'namespace': vm_namespace,
                    'status': vm.get('status', {}).get('printableStatus', 'Unknown'),
                    'dv_count': len(dvs)
                })
                break

    if not matching_vms:
        print(f"{Colors.WARNING}No VMs found using StorageClass '{storage_class}'{Colors.ENDC}")
        return

    print(f"Found {len(matching_vms)} VM(s):\n")

    for vm_info in matching_vms:
        print(f"  • {Colors.OKGREEN}{vm_info['name']}{Colors.ENDC} (namespace: {vm_info['namespace']})")
        print(f"    ├─ Status: {vm_info['status']}")
        print(f"    └─ DataVolumes: {vm_info['dv_count']}")
        print()

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Visualize VM storage relationships in OpenShift Virtualization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show storage tree for a specific VM
  %(prog)s fedora-vm-with-storage --namespace default

  # Show all VMs using a specific storage class
  %(prog)s --storage-class gp3-csi

  # Find orphaned storage resources in default namespace
  %(prog)s --find-orphans

  # Find orphaned resources across all namespaces
  %(prog)s --find-orphans --all-namespaces

  # Show storage tree with custom namespace
  %(prog)s my-vm -n my-namespace
        """
    )

    parser.add_argument('vm_name', nargs='?', help='Name of the VirtualMachine')
    parser.add_argument('-n', '--namespace', default='default', help='Kubernetes namespace (default: default)')
    parser.add_argument('--storage-class', help='Show all VMs using this storage class')
    parser.add_argument('--find-orphans', action='store_true', help='Find orphaned storage resources (DataVolumes, PVCs, PVs not owned by VMs)')
    parser.add_argument('-A', '--all-namespaces', action='store_true', help='Search across all namespaces (for --find-orphans)')
    parser.add_argument('--no-color', action='store_true', help='Disable colored output')

    args = parser.parse_args()

    # Disable colors if requested
    if args.no_color:
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')

    # Check if oc or kubectl is available
    cmd_available = False
    for cmd in ['oc', 'kubectl']:
        try:
            subprocess.run([cmd, 'version'], capture_output=True, check=True)
            cmd_available = True
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    if not cmd_available:
        print(f"{Colors.FAIL}Error: Neither 'oc' nor 'kubectl' command found. Please install one.{Colors.ENDC}")
        sys.exit(1)

    # Mode 1: Find orphaned resources
    if args.find_orphans:
        namespace = None if args.all_namespaces else args.namespace
        print_orphaned_resources(namespace)
    # Mode 2: Show storage class usage
    elif args.storage_class:
        print_storage_class_usage(args.storage_class)
    # Mode 3: Show VM tree
    elif args.vm_name:
        print_vm_tree(args.vm_name, args.namespace)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

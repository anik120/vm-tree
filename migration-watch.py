#!/usr/bin/env python3
"""
migration-watch.py - Monitor storage migration progress in real-time

Watches DataVolumes being migrated and shows progress, status, and errors.

Usage:
    ./migration-watch.py --namespace default
    ./migration-watch.py --namespace default --storage-class standard-fast
    ./migration-watch.py --all-namespaces

Example:
    # Watch all migrations in default namespace
    ./migration-watch.py -n default

    # Watch migrations to specific storage class
    ./migration-watch.py -n default --to-sc standard-fast

    # Watch across all namespaces
    ./migration-watch.py --all-namespaces
"""

import argparse
import json
import subprocess
import sys
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import os


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
    CLEAR_LINE = '\033[K'
    CLEAR_SCREEN = '\033[2J'
    CURSOR_HOME = '\033[H'


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


def get_all_datavolumes(namespace: Optional[str] = None) -> List[Dict]:
    """Get all DataVolumes"""
    cmd = ['get', 'dv']
    if namespace:
        cmd.extend(['-n', namespace])
    else:
        cmd.append('--all-namespaces')

    result = run_kubectl(cmd, check=False)
    return result.get('items', []) if result else []


def get_migration_datavolumes(namespace: Optional[str] = None, target_sc: Optional[str] = None) -> List[Dict]:
    """Get DataVolumes that are part of a migration"""
    all_dvs = get_all_datavolumes(namespace)
    migration_dvs = []

    for dv in all_dvs:
        labels = dv.get('metadata', {}).get('labels', {})

        # Check if this is a migration DataVolume (has our label)
        if labels.get('storage-migration') == 'true':
            # If target_sc specified, filter by it
            if target_sc:
                dv_sc = dv.get('spec', {}).get('storage', {}).get('storageClassName')
                if dv_sc == target_sc:
                    migration_dvs.append(dv)
            else:
                migration_dvs.append(dv)

    return migration_dvs


def calculate_age(timestamp_str: str) -> str:
    """Calculate age from timestamp"""
    try:
        created = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age = now - created

        if age.days > 0:
            return f"{age.days}d"
        elif age.seconds > 3600:
            return f"{age.seconds // 3600}h"
        elif age.seconds > 60:
            return f"{age.seconds // 60}m"
        else:
            return f"{age.seconds}s"
    except:
        return "unknown"


def get_progress_bar(progress: Optional[str], width: int = 20) -> str:
    """Generate a progress bar"""
    if not progress or progress == "N/A":
        return f"[{'?' * width}]"

    try:
        # Parse percentage (e.g., "45.2%" -> 45.2)
        percent = float(progress.rstrip('%'))
        filled = int((percent / 100) * width)
        empty = width - filled

        bar = f"[{'=' * filled}{' ' * empty}] {percent:.1f}%"
        return bar
    except:
        return f"[{'?' * width}] {progress}"


def get_phase_color(phase: str) -> str:
    """Get color for phase"""
    phase_colors = {
        'Succeeded': Colors.OKGREEN,
        'Bound': Colors.OKGREEN,
        'Running': Colors.OKCYAN,
        'ImportInProgress': Colors.OKCYAN,
        'CloneInProgress': Colors.OKCYAN,
        'Pending': Colors.WARNING,
        'WaitForFirstConsumer': Colors.WARNING,
        'Failed': Colors.FAIL,
        'Unknown': Colors.WARNING,
    }
    return phase_colors.get(phase, '')


def clear_screen():
    """Clear terminal screen"""
    print(Colors.CLEAR_SCREEN + Colors.CURSOR_HOME, end='')


def print_migration_status(dvs: List[Dict], namespace_filter: Optional[str] = None):
    """Print current migration status"""
    if not dvs:
        print(f"{Colors.WARNING}No migration DataVolumes found.{Colors.ENDC}")
        print()
        print("DataVolumes created by storage-migration.py have the label:")
        print("  storage-migration: true")
        return

    # Calculate statistics
    stats = {
        'total': len(dvs),
        'succeeded': 0,
        'bound': 0,
        'in_progress': 0,
        'pending': 0,
        'failed': 0,
        'unknown': 0,
    }

    for dv in dvs:
        phase = dv.get('status', {}).get('phase', 'Unknown')
        if phase == 'Succeeded':
            stats['succeeded'] += 1
        elif phase == 'Bound':
            stats['bound'] += 1
        elif phase in ['ImportInProgress', 'CloneInProgress', 'Running']:
            stats['in_progress'] += 1
        elif phase in ['Pending', 'WaitForFirstConsumer']:
            stats['pending'] += 1
        elif phase == 'Failed':
            stats['failed'] += 1
        else:
            stats['unknown'] += 1

    # Print header
    print("=" * 100)
    print(f"  {Colors.BOLD}STORAGE MIGRATION PROGRESS{Colors.ENDC}")
    if namespace_filter:
        print(f"  Namespace: {namespace_filter}")
    else:
        print(f"  All Namespaces")
    print(f"  Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    print()

    # Print statistics
    total = stats['total']
    completed = stats['succeeded'] + stats['bound']
    completion_pct = (completed / total * 100) if total > 0 else 0

    print(f"  {Colors.BOLD}Summary:{Colors.ENDC}")
    print(f"    Total DataVolumes:    {total}")
    print(f"    {Colors.OKGREEN}✅ Completed:{Colors.ENDC}         {completed} ({completion_pct:.1f}%)")
    print(f"    {Colors.OKCYAN}⏳ In Progress:{Colors.ENDC}       {stats['in_progress']}")
    print(f"    {Colors.WARNING}⏸  Pending:{Colors.ENDC}          {stats['pending']}")
    print(f"    {Colors.FAIL}❌ Failed:{Colors.ENDC}           {stats['failed']}")
    if stats['unknown'] > 0:
        print(f"    {Colors.WARNING}❓ Unknown:{Colors.ENDC}          {stats['unknown']}")
    print()

    # Overall progress bar
    overall_progress = f"{completion_pct:.1f}%"
    overall_bar = get_progress_bar(overall_progress, width=40)
    print(f"  {Colors.BOLD}Overall Progress:{Colors.ENDC} {overall_bar}")
    print()
    print("=" * 100)
    print()

    # Print table header
    print(f"{'NAMESPACE':<20} {'NAME':<30} {'PHASE':<20} {'PROGRESS':<25} {'AGE':<8}")
    print("-" * 100)

    # Print each DataVolume
    for dv in dvs:
        ns = dv['metadata']['namespace']
        name = dv['metadata']['name']
        phase = dv.get('status', {}).get('phase', 'Unknown')
        progress = dv.get('status', {}).get('progress', 'N/A')
        created = dv['metadata'].get('creationTimestamp', '')
        age = calculate_age(created)

        # Truncate long names
        if len(name) > 28:
            name = name[:25] + "..."

        # Color the phase
        phase_color = get_phase_color(phase)
        colored_phase = f"{phase_color}{phase}{Colors.ENDC}"

        # Progress bar for in-progress items
        if phase in ['ImportInProgress', 'CloneInProgress'] and progress != 'N/A':
            progress_display = get_progress_bar(progress, width=15)
        elif phase == 'Succeeded' or phase == 'Bound':
            progress_display = f"{Colors.OKGREEN}{'=' * 15}{Colors.ENDC} 100%"
        elif phase == 'Failed':
            progress_display = f"{Colors.FAIL}{'X' * 15}{Colors.ENDC} Failed"
        else:
            progress_display = f"{'·' * 15} {progress}"

        print(f"{ns:<20} {name:<30} {colored_phase:<29} {progress_display:<34} {age:<8}")

    print()

    # Show errors if any
    failed_dvs = [dv for dv in dvs if dv.get('status', {}).get('phase') == 'Failed']
    if failed_dvs:
        print("=" * 100)
        print(f"  {Colors.FAIL}ERRORS:{Colors.ENDC}")
        print("=" * 100)
        for dv in failed_dvs:
            name = dv['metadata']['name']
            ns = dv['metadata']['namespace']
            conditions = dv.get('status', {}).get('conditions', [])

            print(f"\n  {Colors.FAIL}❌ {ns}/{name}{Colors.ENDC}")
            for condition in conditions:
                if condition.get('status') == 'False':
                    reason = condition.get('reason', 'Unknown')
                    message = condition.get('message', 'No message')
                    print(f"     Reason: {reason}")
                    print(f"     Message: {message}")
        print()


def watch_migration(namespace: Optional[str] = None, target_sc: Optional[str] = None,
                   refresh_interval: int = 5):
    """Watch migration progress and update display"""
    try:
        iteration = 0
        while True:
            # Clear screen on subsequent iterations
            if iteration > 0:
                clear_screen()

            # Get migration DataVolumes
            dvs = get_migration_datavolumes(namespace, target_sc)

            # Print status
            print_migration_status(dvs, namespace)

            # Check if all completed
            all_done = True
            if dvs:
                for dv in dvs:
                    phase = dv.get('status', {}).get('phase', 'Unknown')
                    if phase not in ['Succeeded', 'Bound', 'Failed']:
                        all_done = False
                        break

            if all_done and dvs:
                print(f"{Colors.OKGREEN}✅ All migrations completed or failed.{Colors.ENDC}")
                print()
                print("Next steps:")
                print("  1. Verify VMs are working: kubectl get vm -A")
                print("  2. Find orphaned resources: ./vm-tree.py --find-orphans")
                print("  3. Clean up old DataVolumes")
                break

            # Wait before next refresh
            print(f"Refreshing in {refresh_interval}s... (Press Ctrl+C to stop)")
            time.sleep(refresh_interval)
            iteration += 1

    except KeyboardInterrupt:
        print()
        print(f"{Colors.WARNING}Monitoring stopped by user.{Colors.ENDC}")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='Monitor storage migration progress in real-time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Watch migrations in default namespace
  %(prog)s -n default

  # Watch migrations to specific storage class
  %(prog)s -n default --to-sc standard-fast

  # Watch across all namespaces
  %(prog)s --all-namespaces

  # Watch with custom refresh interval
  %(prog)s -n default --refresh 10
        """
    )

    parser.add_argument('-n', '--namespace', help='Kubernetes namespace')
    parser.add_argument('-A', '--all-namespaces', action='store_true',
                        help='Watch across all namespaces')
    parser.add_argument('--to-sc', '--target-storage-class', dest='target_sc',
                        help='Filter by target storage class')
    parser.add_argument('--refresh', type=int, default=5,
                        help='Refresh interval in seconds (default: 5)')
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

    # Determine namespace
    namespace = None if args.all_namespaces else (args.namespace or 'default')

    # Start watching
    watch_migration(namespace, args.target_sc, args.refresh)


if __name__ == '__main__':
    main()

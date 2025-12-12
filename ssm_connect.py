#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "boto3",
#   "tabulate",
# ]
# ///

import boto3
import sys
import subprocess
import signal
from tabulate import tabulate

# --- Helper Functions ---

def get_ssm_ready_instances(ssm_client):
    """Fetches a set of all instance IDs that are online and managed by SSM."""
    ssm_ready_instances = set()
    try:
        paginator = ssm_client.get_paginator('describe_instance_information')
        for page in paginator.paginate(Filters=[{'Key': 'PingStatus', 'Values': ['Online']}]):
            for info in page['InstanceInformationList']:
                ssm_ready_instances.add(info['InstanceId'])
    except Exception:
        # Fail silently on permission errors, just assume none are ready
        pass
    return ssm_ready_instances

def get_image_names(ec2_client, image_ids):
    """Resolves a list of Image IDs (AMIs) to their human-readable Names."""
    if not image_ids:
        return {}
    image_map = {}
    try:
        unique_ids = list(set(image_ids))
        response = ec2_client.describe_images(ImageIds=unique_ids)
        for img in response['Images']:
            image_map[img['ImageId']] = img.get('Name', img['ImageId'])
    except Exception:
        pass
    return image_map

# --- Main Logic ---

def list_and_select_instance():
    filter_term = None
    if len(sys.argv) > 1:
        filter_term = sys.argv[1].lower()
        print(f"Applying filter: Showing instances with name containing '{sys.argv[1]}'")
        print("-" * 70)

    try:
        ec2_client = boto3.client('ec2')
        ssm_client = boto3.client('ssm')

        ssm_ready_instances = get_ssm_ready_instances(ssm_client)
        response = ec2_client.describe_instances()

    except Exception as e:
        print(f"Error fetching AWS data: {e}")
        sys.exit(1)

    # 1. Collect Data
    raw_rows = []
    image_ids_to_fetch = []

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            name = "N/A"
            if 'Tags' in instance:
                for tag in instance['Tags']:
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break

            if filter_term and filter_term not in name.lower():
                continue

            instance_state = instance['State']['Name']
            if instance_state == 'terminated':
                continue

            instance_id = instance['InstanceId']
            ip_address = instance.get('PublicIpAddress') or instance.get('PrivateIpAddress') or 'N/A'
            launch_time = instance['LaunchTime'].strftime("%Y-%m-%d %H:%M")
            image_id = instance.get('ImageId', 'N/A')

            if image_id != 'N/A':
                image_ids_to_fetch.append(image_id)

            is_ssm_ready = instance_id in ssm_ready_instances

            raw_rows.append({
                'name': name,
                'id': instance_id,
                'ip': ip_address,
                'type': instance['InstanceType'],
                'status': instance_state,
                'ssm_ready': is_ssm_ready,
                'launch_time': launch_time,
                'image_id': image_id
            })

    if not raw_rows:
        print("No matching EC2 instances found.")
        sys.exit(0)

    # 2. Fetch Image Names & Sort
    ami_name_map = get_image_names(ec2_client, image_ids_to_fetch)
    raw_rows.sort(key=lambda x: x['name'].lower())

    # 3. Build Table
    table_data = []
    instance_map = {}
    counter = 1

    for row in raw_rows:
        ami_name = ami_name_map.get(row['image_id'], row['image_id'])
        ssm_str = "Yes" if row['ssm_ready'] else "No"

        table_data.append([
            counter, row['name'], row['id'], row['ip'],
            row['type'], row['status'], ssm_str, row['launch_time'], ami_name
        ])

        instance_map[counter] = row
        counter += 1

    headers = ["#", "Name", "Instance ID", "IP", "Type", "Status", "SSM", "Launch", "Image"]
    print(f"\nFound {len(table_data)} EC2 instance(s):")
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print("-" * 70)

    # 4. Selection Loop (Clean Exit on Ctrl+C handled in main block)
    while True:
        try:
            choice_str = input(f"Enter # to connect (1-{len(instance_map)}) or 'q' to quit: ")
            if choice_str.lower() == 'q':
                sys.exit(0)

            choice = int(choice_str)
            if choice in instance_map:
                if not instance_map[choice]['ssm_ready']:
                    print(f"[ERROR] '{instance_map[choice]['name']}' is not SSM Ready (Status: {instance_map[choice]['status']}).")
                    continue
                else:
                    target_instance_id = instance_map[choice]['id']
                    connect_to_ssm(target_instance_id)
                    break
            else:
                print("Invalid number.")
        except ValueError:
            print("Invalid input.")

def connect_to_ssm(instance_id):
    """Starts session, ignoring Python-level Ctrl+C so the session stays alive."""
    print(f"\nAttempting to start SSM session for: {instance_id}...")
    command = ['aws', 'ssm', 'start-session', '--target', instance_id]

    try:
        # Save the original signal handler
        original_handler = signal.getsignal(signal.SIGINT)

        # Tell Python to IGNORE Ctrl+C.
        # The child process (AWS CLI) will still receive it and handle it (e.g., stopping a ping).
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        subprocess.run(command, check=True)
        print(f"\nSSM session for {instance_id} ended.")

    except FileNotFoundError:
        print("\nERROR: AWS CLI not found.")
    except subprocess.CalledProcessError as e:
        print(f"\nSSM Connection failed (Code: {e.returncode}).")
    finally:
        # Restore normal Ctrl+C behavior for the rest of the script
        signal.signal(signal.SIGINT, original_handler)

if __name__ == "__main__":
    try:
        list_and_select_instance()
    except KeyboardInterrupt:
        # This catches Ctrl+C during the menu selection phase
        print("\n\nOperation cancelled.")
        sys.exit(0)

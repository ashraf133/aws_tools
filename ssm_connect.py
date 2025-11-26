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
from tabulate import tabulate

def get_ssm_ready_instances(ssm_client):
    """
    Fetches a set of all instance IDs that are online and managed by SSM.
    """
    ssm_ready_instances = set()
    try:
        paginator = ssm_client.get_paginator('describe_instance_information')
        for page in paginator.paginate(Filters=[{'Key': 'PingStatus', 'Values': ['Online']}]):
            for info in page['InstanceInformationList']:
                ssm_ready_instances.add(info['InstanceId'])
    except Exception as e:
        print(f"\nWarning: Could not get SSM instance information. Is 'ssm:DescribeInstanceInformation' allowed?")
        print(f"Details: {e}\n")
    return ssm_ready_instances

def list_and_select_instance():
    """
    Fetches ALL EC2 instances (running, stopped, etc), displays them,
    and prompts the user to select one for an SSM session.
    """

    # --- Get the filter term from the command line ---
    filter_term = None
    if len(sys.argv) > 1:
        # Use the first argument after the script name as the filter
        filter_term = sys.argv[1].lower()
        print(f"Applying filter: Showing instances with name containing '{sys.argv[1]}'")
        print("-" * 70)

    try:
        ec2_client = boto3.client('ec2')
        ssm_client = boto3.client('ssm')

        # --- Get all SSM-ready instances (silently) ---
        ssm_ready_instances = get_ssm_ready_instances(ssm_client)

        # --- UPDATED: Removed the 'running' filter to show ALL instances ---
        # This will now return Running, Stopped, Stopping, Pending, etc.
        response = ec2_client.describe_instances()

    except Exception as e:
        print(f"Error fetching AWS data. Check your credentials and permissions.")
        print(f"Details: {e}")
        sys.exit(1)

    table_data = []
    instance_map = {}  # Maps the choice number to instance data
    counter = 1

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            instance_type = instance['InstanceType']

            # --- Get instance state (e.g., running, stopped) ---
            instance_state = instance['State']['Name']

            # Optional: specific check to hide 'terminated' instances if they clutter the view
            if instance_state == 'terminated':
                continue

            # Find the 'Name' tag
            name = "N/A"
            if 'Tags' in instance:
                for tag in instance['Tags']:
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break

            # --- Apply the filter logic ---
            if filter_term and filter_term not in name.lower():
                continue  # Skip this instance, it doesn't match the filter

            # Get Public or Private IP
            ip_address = instance.get('PublicIpAddress') or instance.get('PrivateIpAddress') or 'N/A'

            # --- Check SSM availability ---
            # Note: Stopped instances will naturally be False here
            is_ssm_ready = instance_id in ssm_ready_instances
            ssm_available_str = "Yes" if is_ssm_ready else "No"

            # Add data for the table
            table_data.append([
                counter, name, instance_id, ip_address,
                instance_type, instance_state, ssm_available_str
            ])

            # Map the counter to the instance ID for selection
            instance_map[counter] = {
                'id': instance_id,
                'name': name,
                'ssm_available': is_ssm_ready,
                'state': instance_state
            }

            counter += 1

    # --- Updated "no instances" and count message ---
    if not table_data:
        print("="*70)
        if filter_term:
            print(f"No instances found with a name matching '{filter_term}'.")
        else:
            print("No EC2 instances found in this region.")
        print("="*70)
        sys.exit(0)

    # Display the table
    headers = ["#", "Name", "Instance ID", "IP Address", "Type", "Status", "SSM Ready"]
    print(f"\nFound {len(table_data)} EC2 instance(s):")
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print("-" * 70)

    # Get user choice
    choice = 0
    while True:
        try:
            choice_str = input(f"Enter the number (#) of the instance to connect to (1-{len(instance_map)}) or 'q' to quit: ")

            if choice_str.lower() == 'q':
                print("Exiting.")
                sys.exit(0)

            choice = int(choice_str)

            if choice in instance_map:
                # --- Check if SSM is available before breaking ---
                if not instance_map[choice]['ssm_available']:
                    # Provide a specific error if the instance is stopped
                    status = instance_map[choice]['state']
                    print(f"\n[ERROR] Cannot connect to '{instance_map[choice]['name']}'.")
                    print(f"Current Status: {status.upper()}")
                    print(f"SSM requires the instance to be Running and the agent to be active.\n")
                    continue # Re-ask the user
                else:
                    break  # Valid choice
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(instance_map)}.")

        except ValueError:
            print("Invalid input. Please enter a number.")

    # Get the instance ID from the user's choice
    target_instance_id = instance_map[choice]['id']
    connect_to_ssm(target_instance_id)

def connect_to_ssm(instance_id):
    """
    Starts an AWS CLI subprocess to connect to the target instance via SSM.
    """
    print(f"\nAttempting to start SSM session for: {instance_id}...")

    # This is the command that will be run
    command = ['aws', 'ssm', 'start-session', '--target', instance_id]

    try:
        subprocess.run(command, check=True)
        print(f"\nSSM session for {instance_id} ended.")

    except FileNotFoundError:
        print("\n" + "="*50)
        print("ERROR: AWS CLI not found.")
        print("Please ensure the AWS CLI is installed and in your system's PATH.")
        print("="*50)
        sys.exit(1)

    except subprocess.CalledProcessError as e:
        print("\n" + "="*50)
        print(f"Error starting SSM session (Code: {e.returncode})")
        print("Please check the following:")
        print("1. Is the AWS Session Manager plugin installed?")
        print("2. Is the instance SSM-managed (agent running, IAM role attached)?")
        print("3. Do your AWS credentials have 'ssm:StartSession' permissions?")
        print("="*50)
        sys.exit(1)

if __name__ == "__main__":
    list_and_select_instance()

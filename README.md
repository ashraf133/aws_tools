# EC2 SSM Connect Script

A zero-dependency\* Python script to list EC2 instances and connect to them via AWS Systems Manager (SSM) without SSH keys.

## 📋 Prerequisites

Before running this script, ensure you have the following setup.

### 1\. Local Tools (Client-Side)

You need these tools installed on your computer:

  * **[uv](https://github.com/astral-sh/uv):** Used to run the script and handle Python dependencies automatically.
    ```bash
    # Install uv (macOS/Linux)
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```
  * **[AWS CLI](https://aws.amazon.com/cli/):** The script relies on the CLI for credential management.
  * **[Session Manager Plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html):** (Critical) This acts as the bridge for the interactive shell.
      * *If you see "Command not found" or "Plugin not found" errors, this is missing.*

### 2\. AWS Credentials

Your local terminal must be authenticated with AWS.

```bash
aws configure
# Or if using SSO:
aws sso login
```

### 3\. AWS Permissions (IAM)

#### For Your User (Local)

Your AWS user/role needs permission to list instances and start sessions.

  * `ec2:DescribeInstances`
  * `ssm:DescribeInstanceInformation` (Used to check if SSM is ready)
  * `ssm:StartSession`

#### For the EC2 Instance (Remote)

The target EC2 instances must meet three criteria:

1.  **SSM Agent:** Installed and running (Default on Amazon Linux 2/2023).
2.  **IAM Role:** The instance must have an IAM profile attached with the **`AmazonSSMManagedInstanceCore`** policy.
3.  **Network:** The instance must have outbound internet access (via NAT Gateway or Public IP) to talk to the SSM service.

-----

## 🔄 How It Works (The Flow)

1.  **Discovery:** The script uses `boto3` to fetch all EC2 instances and cross-references them with the SSM service to see which are "Online".
2.  **Selection:** You pick an instance from the interactive table.
3.  **Connection:** The script constructs an AWS CLI command (`aws ssm start-session ...`).
4.  **Handover:** The script executes the command, handing control over to the **Session Manager Plugin**, which opens the shell.

-----

## 🚀 How to Run

This script uses `uv`'s script support. You do not need to manually install `boto3` or create a virtual environment.

### Option 1: Run directly with `uv`

```bash
uv run ssm_connect.py
```

### Option 2: Run as a standalone command

1.  Ensure the first line of the script is:
    ```python
    #!/usr/bin/env -S uv run --script
    ```
2.  Make it executable:
    ```bash
    chmod +x ssm_connect.py
    ```
3.  (Optional) Rename it for convenience:
    ```bash
    mv ssm_connect.py ssm
    ```
4.  Run it:
    ```bash
    ./ssm
    ```

### Filtering Results

You can filter instances by name passing an argument:

```bash
./ssm ldap    # Shows only instances with 'ldap' in the name
./ssm prod    # Shows only instances with 'prod' in the name
```

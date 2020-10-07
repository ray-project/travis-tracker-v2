# Setup Instructions

Assumption: You have valid AWS credentials configured in your shell.

## Step 0: Remote State Resources

_Note: Unless you're deploying into a new AWS Account you shouldn't need to deal with
this step._

To set up the resources necessary you'll go into the remote-state module and
apply it. Like so:

```bash
cd remote-state

terraform init
terraform apply # If the changes are what you expect, enter yes when prompted
```

Now we need to pass our outputs back for the primary module to use

```
terraform output > ../backend.hcl
```

## Step 1: Init

```bash
terraform init -backend-config=./backend.hcl
```

## Step 2: Apply

```bash
terraform apply
```

## Step 3: Manual steps

### Create access keys for our two AWS users:

```bash
aws iam create-access-key --user-name travis-logs-uploader
aws iam create-access-key --user-name travis-site-uploader
```

And stash the keys into the appropriate CI secrets mechanism.

### Update DNS

Grab the cloudfront distribution & ACM validation records and update the
appropriate DNS records.

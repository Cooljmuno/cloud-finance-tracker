# AWS deployment runbook

This repository prepares an AWS environment; it has not provisioned or deployed one. The local app
continues to run at `http://localhost:5173/`. The five Terraform mock tests and 41 deployment-script
tests do not contact a live AWS account. Four Terraform tests simulate plans; one simulates an
apply with the entire AWS provider mocked. That mock apply resolves dependent values without
creating AWS resources. The steps below are the separate, deliberate path to a paid environment.

Run commands from a reviewed `main` checkout of the Git repository directory named
`cloud-finance-tracker`, the directory that contains `compose.yaml`, `backend`, `frontend`, and
`infra`. Directory changes are shown explicitly. Use synthetic data throughout.

## 1. Choose the account, region, and spending allowance

Use an AWS account you control and are permitted to bill. The default application region is
`us-east-2`. Review [AWS Pricing Calculator](https://calculator.aws/) using the actual region and
expected running hours before applying the application plan. This topology is not a free-hosting
promise.

| Resource | What continues to cost money |
| --- | --- |
| RDS PostgreSQL | Instance hours, gp3 storage, and retained backup/snapshot storage |
| Internal ALB | Load-balancer hours and capacity usage, even with zero application tasks |
| ECS Fargate | CPU and memory while service, migration, or bootstrap tasks run |
| Public task IPv4 | Assigned public IPv4 addresses while tasks use them |
| S3 and ECR | Stored frontend versions, Terraform state versions, backend images, and requests |
| CloudFront | Requests, data delivery, and invalidations beyond any applicable allowance |
| Secrets Manager and CloudWatch | Secrets, log ingestion/storage, and configured alarms |
| Cognito and data transfer | Usage according to the enabled features and current regional pricing |

Set an account-level AWS Budget with actual and forecast notifications, and verify its email
delivery. A notification is not a hard spending cap; usage can continue after a threshold. Terraform
does not configure an account-wide billing budget. Stopping only ECS leaves the ALB, RDS, storage,
and other resources present. Use the cleanup procedure when the showcase is finished.

### Occasional AWS demos

Keep local Docker as the normal development and demonstration environment; it creates no AWS
bill. For an AWS showcase once or twice a year, create the complete cloud environment for a
limited window, demonstrate it, then perform the [complete cleanup](#cleanup-and-retained-charges).
The cloud URL is available only while that environment exists. No automatic shutdown or deletion
is configured.

An October 2026 Ohio (`us-east-2`) estimate for the configured small environment is about
`$44.165 / 730 hours × 24 hours = $1.45` in base charges for one day. That base includes one
0.25-vCPU/0.5-GiB task, the ALB, `db.t4g.micro`, 20 GiB of database storage, one public task IPv4
address, two secrets, and three alarms. The rates come from the regional AWS price catalogs for
[ECS][price-ecs], [ALB][price-alb], [RDS][price-rds], [secrets][price-secrets],
[CloudWatch][price-cloudwatch], and [public IPv4][price-ipv4]. Allow roughly **$2–$5 for a light-use
demo day**, before tax and retained storage. This is an estimate with a usage buffer, not a cap;
traffic, build/migration tasks, logs, storage, or a longer running window can increase it. Review
current rates and the actual plan before each launch.

Use the existing setup and cleanup steps in this order:

1. Review the plan and cost for the chosen window, provision, bootstrap, deploy, and verify the
   app. On repeat launches, reuse the retained state bucket rather than creating it again.
2. After demonstrating synthetic data, complete the cleanup procedure. Stopping the app or
   setting ECS to zero does not remove the ALB or RDS costs. Check for retained snapshots, S3
   object versions, and state storage, which can remain billable between demonstrations.
3. Before the next launch, set `deletion_protection = true` again and choose a fresh unique
   `final_snapshot_identifier`. Recreate and verify the cloud workspace; reexport
   `deployment-config.json` and replace GitHub's `AWS_DEPLOYMENT_CONFIG`. New CloudFront and
   Cognito resources can have new URLs and IDs, and previous Cognito users are not recreated
   automatically. Build the frontend using the new settings.

The application secret has a 30-day deletion recovery window. AWS does not charge for a secret
[marked for deletion][secret-delete], but its name remains unavailable for immediate recreation.
For a quick repeat launch, wait for deletion to finish or review a distinct `project_name`; do not
assume an immediate same-name rebuild will work. Retained snapshots and state are separate from
this secret recovery window and still need a retention decision.

## 2. Configure temporary administrator access

Install Git, Docker Desktop, Python 3.11 or later, AWS CLI v2, and the exact Terraform version
required by `infra/aws/versions.tf` (currently 1.16.6). Install Node.js compatible with
`frontend/package.json` if building the frontend outside GitHub Actions. The AWS administrator
needs permission to create the networking, IAM roles, Cognito, and application resources described
in the plan.

Prefer an IAM Identity Center permission set and a named CLI profile. Do not use the account root
user for deployment and do not paste AWS access keys, session tokens, database passwords, or OIDC
tokens into chat, source files, Terraform variables, or GitHub variables.

Choose one profile setup below. If you already have Identity Center access, use its start URL and
SSO region with the preferred SSO method:

```bash
aws configure sso --profile finance-admin
aws sso login --profile finance-admin
```

The Identity Center region may differ from the application region. See
[AWS's CLI SSO setup][aws-sso].

For a personal account with an existing IAM user or federated console identity, Identity Center
setup is not required. With AWS CLI 2.32.0 or later and the `SignInLocalDevelopmentAccess` policy
on that identity, use [AWS's browser login][aws-login] instead. Select the intended nonroot identity.
The process profile below lets Terraform obtain temporary credentials through the CLI without
depending on direct `login_session` support:

```bash
aws configure set region us-east-2 --profile finance-signin
aws login --profile finance-signin
aws configure set credential_process 'aws configure export-credentials --profile finance-signin --format process' --profile finance-admin
aws configure set region us-east-2 --profile finance-admin
```

Use a fresh `finance-admin` profile for this alternative; do not combine its process settings with
an existing SSO setup. Both methods use temporary credentials. For browser login, renew an expired
session with `aws login --profile finance-signin`; do not run the export command by itself or copy
its credential output.

After either setup, select the shared admin profile and verify the billing account:

```bash
export AWS_PROFILE=finance-admin
export AWS_REGION=us-east-2
aws sts get-caller-identity
```

Confirm the returned account ID is the intended account before running Terraform.

Infrastructure administration and application deployment are separate identities. GitHub will
receive a restricted application release role through OIDC; it will not receive this admin profile.

## 3. Create the remote-state bucket

`infra/bootstrap` owns only the Terraform-state bucket. Its first apply uses local bootstrap
state, which is ignored by Git. Retain that directory's state securely so the bucket remains
managed. It does not create the application or database.

```bash
cd infra/bootstrap
cp terraform.tfvars.example terraform.tfvars
```

Edit the ignored `terraform.tfvars`: choose a globally unique state-bucket name and the intended
region using `state_bucket_name` and `aws_region`. Never put credentials or secret values there.
Then initialize, validate, and review:

```bash
terraform init -lockfile=readonly
terraform validate
terraform plan -out=bootstrap.tfplan
terraform show bootstrap.tfplan
```

After confirming that this plan creates only the intended state resources, explicitly apply that
saved plan:

```bash
terraform apply bootstrap.tfplan
cd ../..
```

The bucket uses encryption, versioning, public-access blocking, and a TLS-only policy. The
application backend uses native S3 locking with `use_lockfile = true`; no DynamoDB lock table is
required. Versioning supports recovery from accidental state changes. State and plan files still
deserve restricted access, even though this design keeps application password values outside
Terraform. See [Terraform's S3 backend guidance][s3-backend].

## 4. Set the application inputs and GitHub trust

```bash
cd infra/aws
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
```

Edit `backend.hcl` with the bucket from step 3, a state key dedicated to this application, and the
bucket region. Keep encryption and native locking enabled. Configure the application inputs in
`terraform.tfvars` from the checked-in example. Set `aws_region`, `project_name`, `environment`,
`github_oidc_subject`, and a `final_snapshot_identifier` that will be unique when the database is
eventually deleted. Keep `deletion_protection = true`. Supply existing notification destinations
in `alarm_action_arns` if alerts should reach you; the default empty list has no notification
destination. Defaults intentionally use a small Single-AZ database and one running application task
after the first deployment; they do not promise high availability.

Use an exact subject for the GitHub environment named `production`. GitHub repositories created
after July 15, 2026, opted into immutable subjects, or renamed/transferred after that date can use
numeric IDs in the subject. Older unchanged repositories can retain the earlier format:

| Repository OIDC format | Exact subject shape |
| --- | --- |
| Immutable IDs for this repository | `repo:Cooljmuno@92428715/cloud-finance-tracker@1351595936:environment:production` |
| Legacy names | `repo:Cooljmuno/cloud-finance-tracker:environment:production` |

The IDs above are public repository metadata; forks need their own owner/repository IDs. This
repository was created after July 15, so its default is expected to use the immutable form. Verify
its current OIDC settings because custom subject templates can change the shape further.
Do not substitute `*` or assume the legacy format. Terraform also requires the audience
`sts.amazonaws.com`. The source of truth is [GitHub's current OIDC reference][github-oidc].

AWS accounts can already have an OIDC provider for `https://token.actions.githubusercontent.com`.
If present, set `github_oidc_provider_arn` to its ARN in `terraform.tfvars`; do not try
to create a duplicate. Keep the exact-subject restriction on this application's role either way.

In GitHub, open **Settings → Environments**, create `production`, and set deployment branches and
tags to selected branches with `main` allowed. Protect `main` with the repository CI checks and
pull-request review appropriate for the project. Add a required environment reviewer if desired
and supported by the repository plan. The AWS environment subject does not itself include a branch;
the environment's branch restriction and the workflow's `main` guard both matter.

## 5. Review a real application plan, then explicitly provision

From `infra/aws`:

```bash
terraform init -backend-config=backend.hcl -lockfile=readonly
terraform validate
terraform plan -out=application.tfplan
terraform show application.tfplan
```

Read the resources and replacements, not just the final count. Confirm the billing account,
region, private RDS, security-group sources, exact GitHub trust, database deletion protection,
backup retention, and required final snapshot. Check current RDS engine/class availability in that
account and region if planning reports an unsupported version. Revisit the cost estimate with
these actual resources. A mock-provider test cannot establish live service availability or quotas.

RDS is pinned to PostgreSQL major version `18` with automatic minor upgrades enabled. AWS's
[current release notes][rds-versions] list minor version 18.6, but the configuration does not force
the instance back to that patch after AWS applies a newer compatible minor update. The local
PostgreSQL test image is separately pinned to 18.6.

Only after that review, provision this saved plan:

```bash
terraform apply application.tfplan
terraform output -json deployment_config > ../../deployment-config.json
cd ../..
```

CloudFront and RDS creation can take several minutes. A failed apply can leave resources that
already incur charges; inspect the resulting state and AWS console before deciding to retry or
clean up. Avoid copying a different account's outputs over this configuration.

The `deployment_config` output is public deployment metadata: resource names and ARNs, subnet and
security-group IDs, URLs, and Cognito IDs. It contains no passwords or signing secret. Keep the
generated JSON ignored by Git and do not add secret values to it. The ECS service intentionally
starts at desired count zero; its template image tag is a bootstrap placeholder until the first
release builds a real image.

## 6. Bootstrap the application secret and database login once

The task template deliberately references an unpublished placeholder image. Build and push a real
backend image before bootstrap. Remain signed in as `finance-admin`, start Docker Desktop, and
work from the repository root. With a clean tracked working tree, select the reviewed `main`
commit and verify all four CI jobs for that exact commit:

```bash
git switch main
git pull --ff-only
export FINANCE_RELEASE_SHA="$(git rev-parse HEAD)"
python3 scripts/aws/check_ci.py --repository Cooljmuno/cloud-finance-tracker --sha "$FINANCE_RELEASE_SHA"
export FINANCE_ECR_URL="$(python3 -c 'import json; print(json.load(open("deployment-config.json"))["ecr_repository_url"])')"
export FINANCE_ECR_REGISTRY="${FINANCE_ECR_URL%%/*}"
export FINANCE_ECR_NAME="${FINANCE_ECR_URL#*/}"
aws ecr describe-images --repository-name "$FINANCE_ECR_NAME" --image-ids "imageTag=$FINANCE_RELEASE_SHA" --query 'imageDetails[0].imageDigest' --output text
```

If `describe-images` finds an existing SHA tag, reuse it and skip the next build. If it returns
`ImageNotFoundException`, authenticate Docker and build/push the production image. Stop and
investigate any other error. The `linux/amd64` target matches the Fargate task, including on an
Apple Silicon development machine:

```bash
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$FINANCE_ECR_REGISTRY"
docker buildx build --platform linux/amd64 --target production --tag "$FINANCE_ECR_URL:$FINANCE_RELEASE_SHA" --push backend
```

Resolve the digest of the now-existing image, then pass that immutable reference to bootstrap:

```bash
export FINANCE_IMAGE_DIGEST="$(aws ecr describe-images --repository-name "$FINANCE_ECR_NAME" --image-ids "imageTag=$FINANCE_RELEASE_SHA" --query 'imageDetails[0].imageDigest' --output text)"
python3 scripts/aws/bootstrap_environment.py --config deployment-config.json --image "$FINANCE_ECR_URL@$FINANCE_IMAGE_DIGEST"
```

Do not overwrite an existing commit tag with a newly built image. The repository enforces
immutable tags; a later manual release reuses this same digest.

This administrative helper creates the application's current Secrets Manager value only if it is
absent, generating `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` privately. It does not print the
values or place them in Terraform state. It leaves an existing current value unchanged on retry.
Do not manually put those values into GitHub variables.

The helper runs an isolated Fargate database-bootstrap task. Its separate execution role can inject
the RDS-managed master password and the application password into that task. The opt-in
`bootstrap_database` management command creates or updates `finance_app`, grants connection and
schema creation rights, and verifies the task exits successfully. It does not recreate or wipe the
database. Normal migration and service tasks use `finance_app`, which owns tables it creates,
without master privileges. This setup does not seed demo transactions or import your local data.

The `--image` argument is required and must be a digest in the configured ECR repository. The normal
GitHub deploy role cannot read secrets or pass the bootstrap role, so this step is never silently
performed by a release.

RDS manages its master credential in Secrets Manager. The application password is separate; its
rotation requires coordination between the database login, secret version, and a new task rollout.
Replacing a secret alone does not update existing running tasks. The setup helper does not rotate
an existing current application secret.

## 7. Configure and run the manual GitHub release

Open GitHub **Settings → Environments → production → Environment variables**. Create the variable
`AWS_DEPLOYMENT_CONFIG`, and paste the complete JSON object from `deployment-config.json`. This is
an Actions variable, not a secret containing credentials. The workflow obtains temporary AWS
credentials with OIDC. No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` repository secrets are
needed.

Merge the reviewed infrastructure changes to `main` and wait for its CI run to finish successfully.
Then open **Actions → Deploy to AWS**, click **Run workflow**, and select
`main`. Deployment is manual; a merge does not provision or deploy the environment.

The workflow serializes releases without cancelling one in progress. It first verifies the exact
selected commit has a successful `main` push run with `backend`, `frontend`, `containers`, and
`infrastructure` jobs, before asking
AWS for credentials. A successful pull-request run for another SHA does not satisfy that check.

The release sequence is:

1. Validate deployment metadata and the active AWS account. Build a `linux/amd64` production
   backend image, push an immutable commit-SHA tag to the one ECR repository, and deploy its digest.
   A retry reuses an existing digest for that SHA.
2. Register a candidate using the Terraform task-definition template and that image. Run
   `python manage.py migrate --noinput` as a one-off task with the same candidate. Stop on missing
   tasks, failure, a missing exit status, or a timeout.
3. Update the service to the candidate with one desired task. Wait for stability, then verify that
   the primary deployment is the candidate and completed. An automatic rollback to an older revision
   must be reported as failure, even if the service becomes stable.
4. Build the frontend with the public Cognito and API settings. Upload hashed assets first with
   long immutable caching, other static files next, and `index.html` last with `no-store`. Preserve
   old assets and wait for CloudFront invalidation.

Terraform continues owning infrastructure and the task template, while deployment owns the live
service revision and desired count. A later Terraform apply does not intentionally roll the service
back to its placeholder template.

## 8. Verify the real deployment

Use `frontend_url` from the generated JSON. The API health URL is that hostname plus
`/api/v1/health/`. An initial URL uses the CloudFront-provided HTTPS certificate; no domain purchase
or custom ACM certificate is needed.

1. Confirm the health endpoint returns a successful API/database response through HTTPS, and that
   a missing API route retains an API error rather than returning the React page.
2. Open the app, use Cognito signup, verify your email, and sign in. The local `portfolio-demo`
   password is not a Cognito credential. Start a new cloud workspace with synthetic records.
3. Create an account and category, add and edit a transaction, preview and commit a sample CSV,
   confirm a duplicate retry, then check rules, budgets, and reports.
4. Reload a client route and verify the SPA fallback, then sign out and confirm that authenticated
   data is no longer available. Check one independent second user for owner isolation.
5. Review ECS events, CloudWatch application logs, ALB target health, and the database connection.
   Exercise configured alarm notifications and record their delivery. An alarm with no action
   destination is not an email notification.

Do not claim this environment is deployed or recovery-tested until these checks have actually run.
Rehearse backup restore separately into an isolated database before relying on it for recovery.

## Network and TLS boundaries

The CloudFront hostname is the only public application entry point. S3 is private with OAC.
CloudFront connects to an internal HTTP ALB using a VPC origin; the ALB accepts traffic only from
the service-managed VPC-origin security group. AWS requires an attached Internet gateway for the
VPC origin, but the private origin/database subnets have no Internet route. AWS manages its
CloudFront security group; do not edit it. See [VPC-origin requirements][vpc-origins].

Fargate tasks use separate public subnets and public IP addresses for outbound HTTPS to ECR,
Secrets Manager, and Cognito. Their inbound application rule accepts only the ALB security group
on port 8000. RDS is not publicly accessible and accepts port 5432 only from the task group.
This avoids a NAT gateway but still incurs public IPv4 charges and does not use private-only tasks.

Viewer TLS terminates at CloudFront. CloudFront-to-ALB and ALB-to-task traffic is private HTTP, not
end-to-end TLS. Django recognizes HTTPS using the CloudFront-generated protocol header and validates
the CloudFront hostname. The narrow ALB health-check exception does not disable those protections
on ordinary application paths.

PostgreSQL uses TLS with `verify-full` and the actual RDS hostname. The production image contains
`backend/certs/global-bundle.pem` from the [official RDS trust store][rds-ca], referenced inside the
container as `/app/certs/global-bundle.pem`. The checked-in bundle's SHA-256 is:

```text
90a6f1a7978a1b1b096dca6c57511ca48d3b8cf052f8e704baf358f34ea2f21b
```

Before an RDS CA rotation, review [AWS's certificate guidance][rds-tls], update the bundle from the
official HTTPS source, record its new hash, run production configuration tests, rebuild the image,
and roll tasks while the old and new trust are compatible. Do not bypass a certificate error by
downgrading to `require`, disabling verification, or replacing the RDS hostname with an IP address.

## Failure recovery and rollback limits

| Failure | Expected boundary and next action |
| --- | --- |
| CI or configuration validation fails | AWS release work does not begin; fix the failed input or check |
| Secret is absent | Complete the explicit admin bootstrap; do not add passwords to GitHub |
| Migration task fails | Do not roll the service or publish the frontend; inspect its task and logs |
| ECS candidate fails or rolls back | Report failure; leave frontend publication unstarted and inspect task events/logs |
| Frontend build/upload/invalidation fails | The new API may already be live with the earlier UI; fix and retry the same release |
| A retry finds the immutable SHA image | Reuse that digest; do not overwrite the tag with a new image |

An ECS circuit-breaker rollback needs an earlier completed deployment; the first deployment has
none. A later manual rollback must select a known compatible task revision. It does not reverse
database migrations. Use additive migrations and an expand/contract sequence: add compatible
schema, release code using it, then remove old schema in a later release after the rollback window.
A successful migration can still be incompatible with old code if it was designed incorrectly.
See [ECS circuit-breaker behavior][ecs-rollback].

Frontend releases preserve old hashed assets. To restore an older frontend, rebuild the known
compatible commit with the same environment configuration, publish its assets first and its entry
point last, then invalidate CloudFront. Confirm API compatibility first. The manual release workflow
deploys the selected `main` commit; it is not a general rollback UI.

Use RDS restore to a separate database for disaster recovery, verify the restored data, then review
the endpoint/secret/configuration changes needed to move the application. There is no automatic
restore, schema reversal, or zero-data-loss claim in this milestone.

## Cleanup and retained charges

Do this only when intentionally retiring the AWS environment. Deleting a Terraform working
directory, removing credentials, or stopping local Docker does not delete AWS resources.

1. Disable further manual releases and wait for any active release, migration, or bootstrap task
   to finish. Save required synthetic demonstration data and record the current resource IDs.
2. Decide what to retain. RDS deletion protection is enabled and deletion requests a final snapshot;
   verify its identifier is unique. Retained snapshots continue to incur storage charges.
3. From `infra/aws`, set `deletion_protection = false` in `terraform.tfvars`, review a normal plan,
   and apply that change first. This disables the database, ALB, and Cognito user-pool deletion
   guards. Refresh your browser login if needed. Do not remove resources from state to bypass
   protection.
4. Empty the exact application frontend bucket, including noncurrent versions/delete markers if
   versioning applies, and remove ECR images only after deciding they are no longer needed.
   Neither resource uses an unconditional force-delete shortcut. Do not empty the state bucket.
5. Review and apply a destroy plan from the same application root and backend:

```bash
cd infra/aws
terraform plan -destroy -out=destroy.tfplan
terraform show destroy.tfplan
terraform apply destroy.tfplan
cd ../..
```

6. Follow up on any blocked deletion. CloudFront disable/delete can take time; a failed destroy can
   leave billable resources. Verify ECS tasks, ALB, RDS, network interfaces, buckets, ECR images,
   secrets, log groups, and alarms in the intended account and region.
7. Review retained final/manual snapshots, automated backups, Secrets Manager recovery windows,
   S3 object versions, and any resources outside this Terraform state. Delete retained data only
   after its recovery value is no longer needed. Check Billing/Cost Explorer again after usage
   reporting has caught up. See [RDS deletion and backup options][rds-delete].
8. Keep the state bucket and bootstrap state until the application cleanup and retention decision
   are complete. To retire the state bucket later, securely archive the final state, deliberately
   remove its versions and lock objects, and review removing that bucket's `prevent_destroy`
   lifecycle guard in `infra/bootstrap/main.tf`. Then use the separate bootstrap state to plan and
   destroy its bucket. Removing state history is a separate irreversible data-retention decision;
   `deletion_protection = false` on the application does not disable this independent guard.
9. Remove the GitHub environment variable and any now-unused environment settings. An existing
   account-wide OIDC provider reused by this project belongs to that account and is not deleted
   by this application's destroy.

Stopping tasks alone is a temporary pause, not a full cost shutdown. Review the account afterward
instead of assuming a destroy command or a budget alert establishes a zero balance.

## Verification without an AWS account

The normal CI workflow validates application code, production settings, 41 script tests, and five
Terraform mock tests. To inspect the infrastructure locally without remote state or AWS access,
run initialization with the backend disabled and the committed provider lock file, then validate
and run the mock tests in each Terraform root. Do this in a clean checkout or dedicated working
copy so a live environment's backend configuration is not replaced.

```bash
terraform -chdir=infra/bootstrap init -backend=false -lockfile=readonly
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/bootstrap test
terraform -chdir=infra/aws init -backend=false -lockfile=readonly
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws test
python3 -m unittest discover -s scripts/aws/tests -v
```

The Terraform tests globally replace the AWS provider: one bootstrap plan, three application plans,
and one simulated application apply. The apply resolves the service-managed security-group lookup
after its mock dependencies; it does not call AWS or create cloud resources. The script tests use
controlled AWS CLI responses. These checks do not estimate an actual bill or replace the live
verification above.

[aws-sso]: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html
[aws-login]: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html
[s3-backend]: https://developer.hashicorp.com/terraform/language/backend/s3
[github-oidc]: https://docs.github.com/en/actions/reference/security/oidc
[vpc-origins]: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html
[rds-ca]: https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
[rds-tls]: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html
[rds-delete]: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html
[rds-versions]: https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-versions.html
[ecs-rollback]: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html
[secret-delete]: https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html
[price-ecs]: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/us-east-2/index.json
[price-alb]: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSELB/current/us-east-2/index.json
[price-rds]: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/us-east-2/index.json
[price-secrets]: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSSecretsManager/current/us-east-2/index.json
[price-cloudwatch]: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/us-east-2/index.json
[price-ipv4]: https://aws.amazon.com/vpc/pricing/

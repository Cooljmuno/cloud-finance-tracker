# ADR 0008: Reviewable AWS infrastructure and a separate release boundary

- Status: Accepted for infrastructure preparation; live deployment pending
- Date: 2026-10-18

## Context

The application has a working local product and automated correctness checks. Its portfolio goals
also require an explainable cloud topology, secure production authentication, reproducible
infrastructure, and a release process that cannot quietly skip migrations or publish a frontend
before its API is ready. A small project should avoid a custom domain requirement, a NAT gateway,
and several independently deployed application services merely to look production-like.

No AWS account credentials are configured for this milestone. Static validation, mocked Terraform
tests, and stubbed deployment tests can verify the configuration and failure handling;
they cannot prove account quotas, actual service integration, Cognito email delivery, a restore, or
the final bill. Provisioning remains an explicit administrative step.

## Decision

### A single public entry point and a private API origin

Use the default HTTPS CloudFront hostname initially. Serve static React files from a private S3
REST origin with Origin Access Control. Route `/api/*` through a CloudFront VPC origin to an
internal Application Load Balancer and then Django on ECS Fargate. Use a static-route function for
extensionless client routes; preserve API status codes and disable API caching. Do not globally
rewrite origin `403` or `404` responses into `index.html`.

Use a VPC across two availability zones in `us-east-2`. Private origin/database subnets have no
Internet route. Task subnets route through an attached Internet gateway, and tasks receive public
IP addresses solely to reach ECR, Secrets Manager, and Cognito JWKS without a NAT gateway. The task
security group permits inbound port 8000 only from the ALB security group, and RDS permits port
5432 only from the task security group. This is a deliberate outbound networking and cost tradeoff,
not a claim that the tasks occupy private subnets.

The ALB accepts port 80 only from AWS's service-managed CloudFront VPC-origin security group.
Terraform creates the listener before the VPC origin, then discovers the service-managed group
and adds an ingress rule to the application's ALB group. It does not edit the AWS-managed group.
The Internet gateway required by VPC origins does not give the origin/database subnet an Internet
route. See [AWS's VPC-origin requirements][vpc-origins].

TLS covers the browser-to-CloudFront connection. The VPC-origin and ALB-to-task connections use
private HTTP. Database clients require `sslmode=verify-full`, the actual RDS hostname, and the
bundled official RDS CA. This design does not provide end-to-end TLS. A later custom-domain and
origin-certificate design would be a separate change.

Django trusts only CloudFront's generated `CloudFront-Forwarded-Proto` header for the viewer
protocol. The origin request policy preserves the viewer host and bearer authorization header.
ALB private-IP health requests receive a narrow exception for `GET` or `HEAD` at the exact
`/api/v1/health/` path. Ordinary application paths retain host validation, HTTPS handling, and
Cognito authentication. Local password routes, demo endpoints, and Django admin remain disabled.

### Separate state, application secrets, and database roles

Use an S3 remote-state bucket with encryption, versioning, public-access blocking, a TLS-only
bucket policy, and native S3 locking. A separate bootstrap root creates it using locally retained
bootstrap state. No state, plan files, credentials, or generated environment settings belong in
Git. Keep the state bucket after removing the application until recovery and retention decisions
are complete. [Terraform documents native S3 locking and recommends versioning][s3-backend].

Terraform creates application secret metadata without supplying a secret version. An explicit
administrator script generates the Django signing secret and application database password, then
places them directly into Secrets Manager outside Terraform state. It preserves an existing
current version on retry. RDS manages the master password in its own secret; normal application
tasks never receive that master identity.

An administrative one-off bootstrap task receives the RDS master password through a separate
execution role and creates or updates the `finance_app` login. The role has no superuser, database
creation, role creation, or replication privileges; it can connect and create objects in the
application schema. Normal migrations and application tasks use that application login, so tables
created by migrations belong to it. The management command requires an explicit bootstrap enable
flag. The normal deploy role cannot pass the bootstrap execution role or read either secret.

Secrets Manager supplies values when a task starts. Updating a secret does not update an already
running process. Application-password rotation therefore needs a separately reviewed sequence
that updates the database login and rolls tasks, rather than casually replacing the secret. The
bootstrap helper is idempotent setup, not an automatic rotation service.

### Manual infrastructure administration and constrained application releases

Pin Terraform and the AWS provider, commit provider lock files, and use no third-party Terraform
modules. Keep infrastructure changes in the human administrator's plan/apply workflow. The
application release role has no Terraform-state access and cannot provision the infrastructure.

GitHub assumes a deploy role using OIDC with audience `sts.amazonaws.com` and an exact subject for
the repository's `production` environment. The subject is an explicit Terraform input because
GitHub's July 2026 immutable format includes numeric owner and repository IDs; older unchanged
repositories can retain the name-only format. Match the repository's actual subject, and restrict
the GitHub environment to `main`. An environment subject itself does not encode the branch.
See the [GitHub OIDC reference][github-oidc].

Run deployment only through manual dispatch on `main`, with serialized deployments and no
in-progress cancellation. Before obtaining AWS credentials, check that the repository's official
CI workflow succeeded for that exact `main` push commit. Pass public environment metadata through
the `AWS_DEPLOYMENT_CONFIG` environment variable; do not give the deploy job state or secret values.

Use the commit SHA as an immutable ECR image tag and deploy by digest. Reuse the same existing
digest on a retry. Register a candidate from Terraform's task-definition template, run migrations
using that candidate, and abort unless the one-off task exits successfully. Then update the ECS
service and verify its primary deployment is that candidate and has completed. Waiting for a
stable service alone is insufficient because the ECS circuit breaker can restore an older task.

Only after the backend succeeds, build the Cognito-configured frontend. Upload content-hashed
assets first, other static files next, and `index.html` last. Preserve older assets so a browser
with an earlier entry point can still load them; await CloudFront invalidation. Terraform starts
the service at zero desired tasks, and deployment takes ownership of its desired count and
running task definition. The initial bootstrap tag is not expected to run.

### Recovery and operational limits

Use encrypted Single-AZ RDS with seven-day automated backups, deletion protection, and a required
final snapshot. Pin PostgreSQL major version `18` and enable managed minor updates rather than
forcing the currently supported 18.6 patch after AWS upgrades it. Configure finite log retention
and basic ECS, ALB, and RDS alarms. Notification destinations are optional configuration and must
be supplied and tested before claiming alerts
reach anyone. A single task and Single-AZ database are cost-conscious portfolio defaults, not a
high-availability service-level commitment.

A database migration is not automatically reversed after an application failure. Use additive,
backward-compatible migrations and expand/contract releases. An ECS rollback needs an earlier
compatible revision; a first deployment has none. If frontend publication fails after backend
rollout, the old frontend can remain with the new API. Retrying the same release reuses its image
and reruns idempotent migrations; it does not make arbitrary incompatible schema changes safe.

No budget alert creates a hard spending limit. RDS, ALB, running Fargate tasks, public task IPv4
addresses, storage, secrets, logs, and data transfer are billing drivers. Stopping ECS tasks leaves
most other resources billable. Cleanup must deliberately handle deletion protection, retained
snapshots, nonempty buckets, log retention, and the separate state bucket.

## Consequences

- The cloud design is reproducible and reviewable before a paid environment exists. Live rollout
  and recovery validation remain visible follow-up work.
- Five Terraform tests use a globally mocked AWS provider. Four simulate plans; one simulates an
  apply to resolve the origin security-group lookup after its dependencies. That apply creates no
  real AWS resources and is separate from an administrator applying a live plan.
- One hostname avoids cross-origin browser configuration and an initial domain purchase. Private
  HTTP origin traffic is an explicit security boundary and limitation.
- Normal releases need fewer permissions than infrastructure administration or database bootstrap.
  Application secret values avoid Terraform state and GitHub environment variables.
- Failure checks prioritize preserving a working release and financial data, but do not replace a
  tested backup restore or backward-compatible database changes.
- Two Terraform roots and a one-time secret/database bootstrap add setup steps. The
  [deployment runbook](../deployment.md) makes those steps concrete, including costs and cleanup.

[vpc-origins]: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html
[s3-backend]: https://developer.hashicorp.com/terraform/language/backend/s3
[github-oidc]: https://docs.github.com/en/actions/reference/security/oidc

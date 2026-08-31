# PawGuard Platform – Infrastructure, Deployment Architecture & Environment Specification

**Document Reference:** `DOC-HPE-INFRA-2026-V1`  
**Client Organization:** Hewlett Packard Enterprise (HPE)  
**Project:** PawGuard – Pet Safety, Rescue & Care Management Platform  
**Prepared By:** VPD Technologies Backend Engineering Team  
**Date:** August 31, 2026  
**Status:** Ready for Review & Provisioning  

---

## Executive Summary

This document provides the formal architecture specification, deployment topologies, environment isolation boundaries, and infrastructure requirements requested by the HPE Team for the **PawGuard Platform**.

PawGuard is designed around an asynchronous, multi-tenant backend built with FastAPI, PostgreSQL, Redis, and AWS cloud infrastructure, serving four primary client surfaces:
1. **Public Web Portal** (Adoptions, Lost & Found Reports, Donations, Community CMS)
2. **Admin Management Portal** (User & Staff RBAC, Shelter & Kennel Ops, Medical Records, Inventory)
3. **Rescue Staff Mobile Application** (Field Rescues, Live GPS Dispatch, Push Notifications)
4. **Executive & Coordinator Mobile Application** (Metrics, Financial Analytics, Incident Approval)

---

# 5. Deployment Architecture Flow Diagrams & Data Flow

```
=========================================================================================================
                                     HIGH-LEVEL ARCHITECTURE PIPELINE
=========================================================================================================

  +------------------+     +------------------+     +--------------------+     +---------------------+
  |   Public Web     |     |   Admin Portal   |     |  Rescue Mobile App |     | Executive Mobile App|
  |  (Next.js / Web) |     |  (React / Admin) |     |   (iOS / Android)  |     |   (iOS / Android)   |
  +--------+---------+     +--------+---------+     +---------+----------+     +----------+----------+
           |                        |                         |                           |
           +------------------------+------------+------------+---------------------------+
                                                 |
                                      (HTTPS / TLS 1.3 Requests)
                                                 |
                                                 v
                       +---------------------------------------------------+
                       |        EDGE & SECURITY TIER (AWS CloudFront)      |
                       | - Amazon Route 53 (DNS Routing & Latency Rules)   |
                       | - AWS WAF (DDoS Mitigation, IP Throttling, SQLi)  |
                       | - AWS Certificate Manager (Automated SSL / TLS)   |
                       +-------------------------+-------------------------+
                                                 |
                                                 v
                       +---------------------------------------------------+
                       |      TRAFFIC DISTRIBUTION (Amazon AWS ALB)        |
                       | - Application Load Balancer across Dual AZs       |
                       | - Path-based routing & real-time health checks    |
                       +-------------------------+-------------------------+
                                                 |
                                                 v
                       +---------------------------------------------------+
                       |       APPLICATION COMPUTE (AWS ECS Fargate)       |
                       |                                                   |
                       |  [Task 1: FastAPI Web]     [Task 2: FastAPI Web]  |
                       |  - Auth & RBAC Security    - Validation Pipeline  |
                       |  - Sub-100ms API Execution - ETag HTTP 304 Cache  |
                       +------------+------------------------+-------------+
                                    |                        |
         +--------------------------+                        +--------------------------+
         |                                                                              |
         v                                                                              v
+-----------------------------+                                    +-----------------------------+
|   DATA TIER (Amazon RDS)    |                                    |   CACHE & QUEUE (ElastiCache|
| - PostgreSQL 16 (Multi-AZ)  |                                    | - Redis 7 (In-Memory Cache) |
| - Automated Daily Snapshots |                                    | - RBAC & Session Store      |
| - 50 GB Encrypted gp3 SSD   |                                    | - High-Throughput Job Queue |
+--------------+--------------+                                    +--------------+--------------+
               |                                                                  |
               |                                                                  v
               |                                                   +-----------------------------+
               |                                                   |  ASYNC WORKER (ECS Fargate) |
               |                                                   | - Dedicated ARQ Worker Task |
               |                                                   | - PDF Contract Generator    |
               |                                                   | - Bulk Analytics Processor  |
               +-----------------------------+---------------------+--------------+--------------+
                                             |                                    |
                                             v                                    v
                               +-----------------------------+     +-----------------------------+
                               | OBJECT STORAGE (Amazon S3)  |     | THIRD-PARTY INTEGRATIONS    |
                               | - Pet Photos & Medical Docs |     | - Payment Gateway (Razorpay)|
                               | - Encrypted Donation Pdfs   |     | - Push Alerts (Firebase FCM)|
                               | - Short-lived Presigned URLs|     | - SMS Alerts (Twilio/MSG91) |
                               +-----------------------------+     | - Transactional Mail(SES)   |
                                                                   +-----------------------------+
=========================================================================================================
```

---

## 5.1 Production Environment Architecture (AWS Enterprise Cloud)

```
=========================================================================================================
                                     PRODUCTION AWS CLOUD ARCHITECTURE
=========================================================================================================

 [Clients] ────► [Amazon Route 53] ────► [AWS WAF + CloudFront] ────► [Application Load Balancer]
                                                                                │
 ┌────────────────────────── AWS VPC (Multi-AZ: us-east-1a / us-east-1b) ───────┴────────────────────────┐
 │                                                                                                       │
 │  ┌─── Public Subnets ──────────────────────────────────────────────────────────────────────────────┐  │
 │  │   • Application Load Balancer (ALB)                                                             │  │
 │  │   • AWS NAT Gateways (Secure Outbound Traffic for Private Tasks)                                │  │
 │  └─────────────────────────────────────┬───────────────────────────────────────────────────────────┘  │
 │                                        │ (Round-Robin SSL Forwarding)                                 │
 │  ┌─── Private Application Subnets ─────v───────────────────────────────────────────────────────────┐  │
 │  │                                                                                                 │  │
 │  │   +------------------------------------+             +------------------------------------+     │  │
 │  │   |  ECS Task 1: FastAPI Web Server    |             |  ECS Task 2: FastAPI Web Server    |     │  │
 │  │   |  (0.5 vCPU, 1 GB RAM, Auto-Scaled) |             |  (0.5 vCPU, 1 GB RAM, Auto-Scaled) |     │  │
 │  │   +------------------+-----------------+             +------------------+-----------------+     │  │
 │  │                      │                                                  │                       │  │
 │  │                      +─────────────────────────+────────────────────────+                       │  │
 │  │                                                │                                                │  │
 │  │                                                v                                                │  │
 │  │                              +------------------------------------+                             │  │
 │  │                              |  ECS Task 3: Dedicated ARQ Worker  |                             │  │
 │  │                              |  (0.5 vCPU, 1 GB RAM, Heavy Jobs)  |                             │  │
 │  │                              +-----------------+------------------+                             │  │
 │  └────────────────────────────────────────────────┼────────────────────────────────────────────────┘  │
 │                                                   │                                                   │
 │  ┌─── Private Data Subnets ───────────────────────v────────────────────────────────────────────────┐  │
 │  │                                                                                                 │  │
 │  │   +------------------------------------+             +------------------------------------+     │  │
 │  │   |  Amazon RDS PostgreSQL 16 (Primary)|             |  Amazon ElastiCache Redis 7        |     │  │
 │  │   |  - db.t4g.small (Multi-AZ Standby) |             |  - cache.t4g.micro                 |     │  │
 │  │   |  - 50 GB gp3 SSD (KMS Encrypted)   |             |  - Rate Limiting & Fast Caching    |     │  │
 │  │   +------------------------------------+             +------------------------------------+     │  │
 │  └─────────────────────────────────────────────────────────────────────────────────────────────────┘  │
 └───────────────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                                     │
                             +───────────────────────┴───────────────────────+
                             │                                               │
                             v                                               v
              +-----------------------------+                 +-----------------------------+
              |   Amazon S3 Standard Bucket |                 | External APIs (via NAT GW)  |
              |   • pawguard-prod-assets    |                 | • Razorpay / Stripe Gateway |
              |   • Medical PDFs & Photos   |                 | • Firebase FCM (Push)       |
              |   • 99.999999999% Durability|                 | • Twilio SMS & Amazon SES   |
              +-----------------------------+                 +-----------------------------+
=========================================================================================================
```

---

## 5.2 Staging Environment Architecture (Pre-Production Mirror)

```
=========================================================================================================
                                     STAGING DEPLOYMENT TOPOLOGY
=========================================================================================================

 [Staging Clients]
  • Staging Web (Next.js on Vercel Preview)
  • Staging Admin (React on Vercel Preview)
  • Mobile Staging Builds (Apple TestFlight / Android Internal Testing)
         │
         │ (HTTPS / Test API Traffic)
         v
 +-----------------------------------------------------------------------------------+
 | COMPUTE TIER (Render Pro / Staging AWS Container)                                 |
 |                                                                                   |
 |  [Staging Web API Instance]                  [Staging ARQ Worker Instance]        |
 |  • FastAPI Staging Container                 • Background Jobs Container          |
 |  • Debug & Detailed Trace Logging            • Sandbox PDF & Email Execution      |
 +-----------------------+-----------------------------------+-----------------------+
                         |                                   |
         +---------------+-----------------+                 |
         │                                 │                 │
         v                                 v                 v
 +-----------------------------+   +-----------------------------+   +-----------------------------+
 | STAGING DATABASE            |   | STAGING CACHE               |   | STAGING OBJECT STORAGE      |
 | • PostgreSQL Staging DB     |   | • Upstash Redis Pro / Test  |   | • AWS S3 Bucket             |
 | • Seeded Demo Records       |   | • Cache Testing & Queuing   |   |   (pawguard-staging-media)  |
 +-----------------------------+   +-----------------------------+   +-----------------------------+
                                                   │
                                                   v
                                   +-----------------------------+
                                   | THIRD-PARTY TEST SANDBOXES  |
                                   | • Razorpay Sandbox Test Mode|
                                   | • Firebase Staging App      |
                                   | • Mail Sandbox / Resend Dev |
                                   +-----------------------------+
=========================================================================================================
```

---

## 5.3 Local & Development Environment Architecture

```
=========================================================================================================
                                    DEVELOPMENT / LOCAL ENVIRONMENT
=========================================================================================================

 [Developer Workstation]
  • Frontend Web Dev Server (localhost:3000)
  • Admin Portal Dev Server (localhost:5173)
  • Postman API Collection & Swagger OpenAPI UI (localhost:8000/docs)
         │
         │ (HTTP / Local Network)
         v
 +-----------------------------------------------------------------------------------+
 | LOCAL RUNTIME (Python 3.12 Virtual Environment)                                   |
 | • FastAPI Application running via Uvicorn with auto-reload                        |
 | • Local Environment Variables (.env.local)                                        |
 +-----------------------+-----------------------------------+-----------------------+
                         |                                   |
         +---------------+-----------------+                 |
         │                                 │                 │
         v                                 v                 v
 +-----------------------------+   +-----------------------------+   +-----------------------------+
 | LOCAL DATABASE (Docker)     |   | LOCAL REDIS (Docker)        |   | LOCAL ASSET STORAGE         |
 | • PostgreSQL 16 on :5432    |   | • Redis 7 on :6379          |   | • Local Filesystem / MinIO  |
 | • Alembic Migration Testing |   | • Local Rate-Limit & Cache  |   |   Mock Storage              |
 +-----------------------------+   +-----------------------------+   +-----------------------------+
                                                   │
                                                   v
                                   +-----------------------------+
                                   | LOCAL MOCK HANDLERS         |
                                   | • Mock Payment Webhooks     |
                                   | • Mock Console Log Notifier |
                                   +-----------------------------+
=========================================================================================================
```

---

## 5.4 Step-by-Step Data & Transaction Flow

```
=========================================================================================================
                                     REQUEST LIFECYCLE & EXECUTION FLOW
=========================================================================================================

 [1. Incoming Request]   ──► Web or Mobile client sends HTTPS request with JWT Cookie/Bearer Token.
                                     │
                                     ▼
 [2. Edge Security]      ──► Route 53 routes to CloudFront CDN; AWS WAF inspects for attacks & rate limits.
                                     │
                                     ▼
 [3. Load Balancer]      ──► AWS Application Load Balancer terminates SSL and routes to healthy API task.
                                     │
                                     ▼
 [4. Router & Auth]      ──► FastAPI middleware extracts JWT claims and queries Redis cache in < 2ms.
                                     │
                                     ▼
 [5. RBAC & Validation]  ──► Route dependency verifies required permissions (e.g. system:admin, rescue:write).
                                     │
                                     ▼
 [6. Service Execution]  ──► Service layer executes business rules and initiates atomic database transaction.
                                     │
                                     ▼
 [7. Database Commit]    ──► PostgreSQL executes query via async SQLAlchemy pool with index acceleration.
                                     │
                                     ▼
 [8. Caching & ETag]     ──► Response cached in Redis with SHA-256 ETag; returns HTTP 200 or 304 Not Modified.
                                     │
                                     ▼
 [9. Async Job Queue]    ──► If email, SMS, push, or PDF required, payload published to Redis ARQ queue.
                                     │
                                     ▼
 [10. Worker Processing] ──► Isolated ECS Worker task picks up job, uploads PDF to S3, and triggers external APIs.
=========================================================================================================
```

---

# Complete Infrastructure & Access Summary (Items 1 – 6)

### 1. AWS Production Infrastructure & Cost Estimates
| Component | AWS Technology | Configuration | Estimated Monthly Cost |
| :--- | :--- | :--- | :--- |
| **Compute (Web API)** | AWS ECS Fargate | 2x Tasks (0.5 vCPU, 1 GB RAM, Multi-AZ) | $25 – $35 / mo |
| **Compute (Background Worker)** | AWS ECS Fargate | 1x Task (0.5 vCPU, 1 GB RAM) | $12 – $18 / mo |
| **Primary Database** | Amazon RDS PostgreSQL | db.t4g.small (2 vCPU, 2 GB RAM, 50 GB gp3 SSD) | $35 – $50 / mo |
| **In-Memory Cache** | Amazon ElastiCache Redis | cache.t4g.micro (Single Node / Multi-AZ capable) | $15 – $22 / mo |
| **Networking & Load Balancer** | AWS ALB + VPC | 1x ALB, 2 Public Subnets, 2 Private Subnets | $18 – $22 / mo |
| **Object Storage & CDN** | Amazon S3 + CloudFront | Standard S3 (50 GB media storage + CloudFront CDN) | $5 – $10 / mo |
| **Security & DNS** | Route 53 + ACM + AWS WAF | SSL via ACM (Free), Managed WAF rules | $5 – $10 / mo |
| **Total Estimated AWS Cost** | | | **~$115 – $167 / month** |

*Required IAM Permissions for VPD Team:*
- `AmazonECS_FullAccess` (Deployment and task definition management)
- `AmazonECR_FullAccess` (Container image push and pull)
- `AmazonRDSDataFullAccess` / `AmazonRDSReadOnlyAccess` (Database schema management & telemetry)
- `AmazonS3FullAccess` (Bucket policies, media uploads, and presigned URLs)
- `CloudWatchLogsReadOnlyAccess` (Container log inspection and real-time alerts)

---

### 2. Development & Staging Environments
- **Vercel Pro ($20/seat/mo):** Required for building and hosting the Next.js Public Website and React Admin Portal with preview deployments, custom staging domains, and edge routing.
- **Render Pro / Cloud Dev ($25/mo):** Container runtime for continuous staging backend APIs and automated pull request validation before promotion to AWS ECS.
- **Upstash Redis Pro ($10 – $25/mo):** Low-latency managed serverless Redis for development and staging environments.
- *Lifecycle:* Dev/Staging accounts remain active post-launch to validate ongoing sprints, mobile builds, and security hotfixes before promoting to AWS Production.

---

### 3. Payment Gateway Specifications
- **Proposed Provider:** **Razorpay** (Primary for INR transactions / UPI / NetBanking / Cards) or **Stripe** (International).
- **Integration Architecture:** Webhook-driven asynchronous settlement with idempotent order verification (`pg_order_id`, `pg_payment_id`).
- **Required Credentials from HPE:**
  1. Sandbox API Key ID & API Secret
  2. Webhook Secret Key
  3. Production Merchant Account Access (when ready for go-live)

---

### 4. Mobile Application Release Roadmap
- **Platforms in Scope:** Both **Android** and **iOS** applications are in active scope for:
  - Rescue Field Staff Application
  - Executive Dashboard Application
- **Target Release Milestones:**
  - *Internal TestFlight & Android APK builds:* Current Staging Sprint
  - *Google Play Store & Apple App Store Beta Review:* 3–4 weeks following staging sign-off.
- **Account Provisioning:** HPE to provide Developer role access on Google Play Console and App Store Connect (no root/master credentials required).

---

### 6. Current Development & Module Status
- **Completed & Verified Modules (28/28 Backend Modules Ready):**
  - Custom Authentication & Argon2id Security Core
  - Role-Based Access Control (RBAC) & Dynamic Permissions
  - Core Dogs, Breeds, Medical Records, Vaccinations & Safety Tags
  - Rescue Incident Reporting, GPS Geofencing, Dispatch & Unit Assignment
  - Shelter, Kennels, Foster Management & Capacity Tracking
  - Adoption Application Workflow & Automatic Agreement PDF Generation
  - Inventory, Stock Audits & Fleet Management
  - Donations, Invoicing, Financial Ledger & Payment Webhooks
  - Public Portal CMS (Success Stories, Blog Posts, Location Directory, FAQs)
  - Notifications (In-App, Email, SMS, Firebase Push Notifications)
  - Security Audit Logging & Outbox Event Dispatcher
- **Testing & Verification Status:** 672 unit tests passing, full mypy type verification, clean ruff linting.
- **Current Blockers (Requiring Infrastructure Provisioning):**
  1. Live SMS OTP & Alert verification (Awaiting Twilio / SMS provider credentials).
  2. Live Mobile Push Notification End-to-End Delivery (Awaiting Firebase project linkage).
  3. Live Production Payment Webhook reconciliation (Awaiting Payment Gateway sandbox credentials).
  4. Production Deployment & Verification on AWS ECS Fargate cluster.

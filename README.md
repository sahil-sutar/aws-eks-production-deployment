# Production Two-Tier Web Application on AWS EKS

A containerized, resilient two-tier cloud-native web application deployed on Amazon Elastic Kubernetes Service (EKS) in the `ap-south-1` (Mumbai) region. The application features a Python Flask REST backend and a persistent MySQL database, exposed to the public internet via an AWS Elastic Load Balancer (ELB).

---

## Architecture Overview

```text
       Internet Traffic
              │
              ▼
    [ AWS Load Balancer ] (Classic/Network ELB - ap-south-1)
              │
              ▼ (NodePort Routing: 30000-32767)
    [ backend-service:80 ] (Kubernetes Service - LoadBalancer)
              │
              ▼
    [ Flask Backend Pods ] (Target Port 5000 | 2 Replicas)
              │
              ▼ (CoreDNS internal resolution: mysql-service)
    [ mysql-service:3306 ] (ClusterIP)
              │
              ▼
    [ MySQL Database Pod ] (Database: devopsdb | Table: messages)
```

### Key Highlights
* **Decoupled Architecture:** High-availability application tier decoupled from internal database storage using Kubernetes native `ClusterIP` abstraction.
* **Declarative Configuration:** Decoupled secrets (`mysql-secret`) and environmental configurations (`flask-config`).
* **Self-Healing Probes:** Automated readiness and liveness health checks hooked into `/health`.
* **Production Load Balancing:** Automatic AWS Load Balancer provisioning via Kubernetes Service Controller.

---

## Repository Structure

```text
.
├── k8s/
│   ├── 00-namespace.yaml          # Dedicated namespace (prod-namespace)
│   ├── 01-configmap.yaml          # Environmental configuration (DB Host, DB Name)
│   ├── 02-secret.yaml             # Encrypted credentials for MySQL and Flask
│   ├── 03-mysql-deployment.yaml   # MySQL 8.0 Deployment specification
│   ├── 04-mysql-service.yaml      # Internal ClusterIP service on port 3306
│   ├── 05-flask-deployment.yaml   # Flask backend deployment with health probes
│   └── 06-backend-service.yaml    # Public AWS LoadBalancer service on port 80
└── README.md
```

---

## Prerequisites

Ensure the following tools are installed and authenticated locally:
* [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) configured with access to `ap-south-1`
* [kubectl](https://kubernetes.io/docs/tasks/tools/) matching your EKS cluster version
* [eksctl](https://eksctl.io/) (if managing the cluster lifecycle via CLI)

---

## Deployment Guide

### 1. Provision the Cluster (Optional)

If starting from scratch using `eksctl`:

```bash
eksctl create cluster \
  --name prod-cluster \
  --region ap-south-1 \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 2
```

### 2. Apply Namespace and Configuration

Deploy the core namespace along with the application configuration and secrets:

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-configmap.yaml
kubectl apply -f k8s/02-secret.yaml
```

### 3. Deploy MySQL Database

Deploy the database workload and expose its internal `ClusterIP` service:

```bash
kubectl apply -f k8s/03-mysql-deployment.yaml
kubectl apply -f k8s/04-mysql-service.yaml

# Wait until MySQL is ready
kubectl wait --namespace prod-namespace \
  --for=condition=ready pod \
  --selector=app=mysql \
  --timeout=90s
```

### 4. Initialize Database Schema & Grants

Execute the initial schema migration and ensure application permissions are set:

```bash
kubectl exec -i deployment/mysql-deployment -n prod-namespace -- mysql -u root -pROOT -e "
CREATE DATABASE IF NOT EXISTS devopsdb;
CREATE USER IF NOT EXISTS 'USER'@'%' IDENTIFIED BY 'TES@123';
ALTER USER 'USER'@'%' IDENTIFIED BY 'TES@123';
GRANT ALL PRIVILEGES ON devopsdb.* TO 'USER'@'%';
FLUSH PRIVILEGES;

USE devopsdb;
CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"
```

### 5. Deploy Flask Backend Application & Load Balancer

Deploy the backend application replicas and request an external AWS Load Balancer:

```bash
kubectl apply -f k8s/05-flask-deployment.yaml
kubectl apply -f k8s/06-backend-service.yaml

# Verify deployment rollout
kubectl rollout status deployment/flask-backend -n prod-namespace
```

---

## Verification & Validation

### 1. Retrieve the Public AWS DNS

Fetch the public endpoint provisioned by AWS:

```bash
kubectl get svc backend-service -n prod-namespace
```

Locate the `EXTERNAL-IP` value (e.g., `a0ce9bca961a140c2b9a7bf2d7355254-1859915746.ap-south-1.elb.amazonaws.com`).

### 2. Verify Health Endpoint

```bash
curl -i http://<EXTERNAL-IP>/health
```

Expected response:
```json
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"healthy"}
```

### 3. Web UI Validation

1. Open `http://<EXTERNAL-IP>` in your web browser.
2. Confirm the **Database Status** badge displays **Connected**.
3. Submit a new message in the form to confirm full read/write persistence.

---

## Troubleshooting Matrix

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| **`Access denied for user 'USER'@'%' to database 'devopsdb'`** | User permissions were not flushed or user created without proper DB privileges. | Run `GRANT ALL PRIVILEGES ON devopsdb.* TO 'USER'@'%'; FLUSH PRIVILEGES;` directly inside MySQL. |
| **`Unknown column 'content' in 'field list'`** | Schema mismatch between SQL queries in Flask code and the MySQL table definition. | Alter table schema: `ALTER TABLE messages ADD COLUMN content TEXT;`. |
| **`Field 'message' doesn't have a default value`** | Deprecated column has a `NOT NULL` constraint without a default. | Modify column to accept nulls: `ALTER TABLE messages MODIFY COLUMN message TEXT NULL;` or drop and recreate the table. |
| **`DROP TABLE` or `ALTER TABLE` hangs** | Metadata Lock (MDL) held by active Flask connections during error retries. | Restart the backend deployment: `kubectl rollout restart deployment/flask-backend -n prod-namespace` to release locks. |
| **Service reverts to `ClusterIP`** | Configuration drift between `kubectl patch` and local Git YAML files. | Commit `type: LoadBalancer` directly inside `k8s/06-backend-service.yaml`. |

---

## Teardown & Cost Optimization

To prevent ongoing AWS compute or load balancing charges:

```bash
# 1. Delete LoadBalancer service (deletes the AWS ELB)
kubectl delete svc backend-service -n prod-namespace

# 2. Delete all namespace workloads
kubectl delete namespace prod-namespace

# 3. Destroy EKS Cluster & Node Groups
eksctl delete cluster --name prod-cluster --region ap-south-1

# 4. Verify no billable resources remain
aws elb describe-load-balancers --region ap-south-1 --output table
aws ec2 describe-instances --region ap-south-1 --filters "Name=instance-state-name,Values=running" --output table
aws ec2 describe-volumes --region ap-south-1 --filters "Name=status,Values=available" --output table
```

---


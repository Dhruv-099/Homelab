

# Homelab Infrastructure-as-Code (IaC)

This repository serves as the **Source of Truth** for my homelab. It manages the deployment, configuration, and versioning of all self-hosted services across the HP EliteDesk node.4

---

##  Tech Stack
* **Orchestration:** Docker Compose / Portainer
* **Infrastructure:** Proxmox VE
* **Networking:** Nginx Proxy Manager, Netbird (VPN)
* **Storage:** Local ZFS + AWS S3 (Off-site Backup)
* **Documentation:** [BookStack](http://wiki.bobalhouse.co.in)

---

## Repository Structure

```text

│── bookstack/          # Wiki & Documentation
│── forgejo/            # Git Source Control
│── netbird/            # Mesh VPN Management
│── arr-stack/          # Media Management
├── scripts/                # Automation & Maintenance scripts
│   ├── backup-check.py     # Duplicati status auditor
│   └── node-prune.sh       # Docker resource cleanup
└── .env.example            # Template for environment variables
```

---

## Deployment Workflow

### 1. Adding a New Service
1. Create a directory in `<service-name>`.
2. Add a `docker-compose.yml` file.
3. Define secrets in a local `.env` file.
4. Deploy via Portainer pointing to this repository.

### 2. Maintenance Commands
- Automatic updates done by watchtower
---

## 🛡️ Backup Policy (3-2-1 Strategy)
- **Primary:** Local storage.
- **Secondary:** Daily automated backups via **Duplicati**.
- **Off-site:** Encrypted archives pushed to **AWS S3** (Standard-IA).

---

## 📋 Infrastructure Inventory
| Node Name | Hardware | Role | RAM | NVME| HDD |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PVE-01** | HP EliteDesk 705 | Management / Prod | 32 GB | 512 GB| 1Tb+ 2Tb|

---
*Maintained by Dhruv Bobal.*

#!/usr/bin/env bash
set -euo pipefail

if (( $# < 1 || $# > 2 )) || [[ $# == 2 && "$2" != --with-public-nat ]]; then
  printf 'Usage: bash scripts/provision_gke_demo.sh PROJECT_ID [--with-public-nat]\n' >&2
  exit 2
fi
project_id=$1
public_nat=${2:-}
if [[ ! "$project_id" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  printf 'Invalid Google Cloud project ID: %s\n' "$project_id" >&2
  exit 2
fi

region=asia-southeast1
zone=asia-southeast1-b
network=geolife-cp2
subnet=geolife-cp2-gke
sql_range=geolife-cp2-sql-range
cluster=geolife-cp2
instance=geolife-cp2-pg
node_account_id=geolife-cp2-gke-node
node_account="$node_account_id@$project_id.iam.gserviceaccount.com"
router=geolife-cp2-router
nat_gateway=geolife-cp2-nat
gcp=(gcloud --project="$project_id" --quiet)

resource_missing() {
  local found
  found=$("${gcp[@]}" "$@") || exit 1
  [[ -z "$found" ]]
}

billing=$("${gcp[@]}" billing projects describe "$project_id" --format='value(billingEnabled)')
if [[ "${billing,,}" != true ]]; then
  printf 'Billing is not enabled for %s.\n' "$project_id" >&2
  exit 1
fi

"${gcp[@]}" services enable compute.googleapis.com container.googleapis.com \
  sqladmin.googleapis.com servicenetworking.googleapis.com iam.googleapis.com

cluster_status=$("${gcp[@]}" container clusters list --location="$zone" \
  --filter="name=$cluster" --format='value(status)')
if [[ -n "$cluster_status" && "$cluster_status" != RUNNING ]]; then
  printf 'Cluster %s in %s has status %s. Resolve the cluster state before rerunning.\n' \
    "$cluster" "$zone" "$cluster_status" >&2
  exit 1
fi

if resource_missing compute networks list --filter="name=$network" --format='value(name)'; then
  "${gcp[@]}" compute networks create "$network" --subnet-mode=custom
fi
if resource_missing compute networks subnets list --regions="$region" \
  --filter="name=$subnet" --format='value(name)'; then
  "${gcp[@]}" compute networks subnets create "$subnet" --network="$network" --region="$region" \
    --range=10.42.0.0/24 --secondary-range=geolife-pods=10.48.0.0/16,geolife-services=10.49.0.0/20
fi
if resource_missing compute addresses list --global --filter="name=$sql_range" --format='value(name)'; then
  "${gcp[@]}" compute addresses create "$sql_range" --global --purpose=VPC_PEERING \
    --addresses=10.90.0.0 --prefix-length=16 --network="$network"
fi
if resource_missing services vpc-peerings list --network="$network" \
  --service=servicenetworking.googleapis.com --format='value(peering)'; then
  "${gcp[@]}" services vpc-peerings connect --network="$network" \
    --service=servicenetworking.googleapis.com --ranges="$sql_range"
fi

if resource_missing iam service-accounts list --filter="email=$node_account" --format='value(email)'; then
  "${gcp[@]}" iam service-accounts create "$node_account_id" --display-name='GeoLife CP2 GKE nodes'
fi
for delay in 5 10 20 40 60 0; do
  if binding_output=$("${gcp[@]}" projects add-iam-policy-binding "$project_id" \
    --member="serviceAccount:$node_account" --role=roles/container.defaultNodeServiceAccount \
    --condition=None --format=none 2>&1); then
    break
  fi
  if [[ "$delay" == 0 || "$binding_output" != *"Service account $node_account does not exist"* ]]; then
    printf '%s\n' "$binding_output" >&2
    exit 1
  fi
  printf 'Waiting %s seconds for the GKE node service account to propagate.\n' "$delay"
  sleep "$delay"
done

if [[ -z "$cluster_status" ]]; then
  "${gcp[@]}" container clusters create "$cluster" --zone="$zone" --release-channel=regular \
    --machine-type=e2-standard-2 --num-nodes=2 --disk-type=pd-balanced --disk-size=30 \
    --network="$network" --subnetwork="$subnet" --enable-ip-alias --enable-private-nodes \
    --cluster-secondary-range-name=geolife-pods --services-secondary-range-name=geolife-services \
    --enable-dns-access --no-enable-ip-access --service-account="$node_account" \
    --workload-pool="$project_id.svc.id.goog"
fi

"${gcp[@]}" container clusters get-credentials "$cluster" --zone="$zone" --dns-endpoint
kubectl wait --for=condition=Ready node --all --timeout=180s
kubectl get nodes -o wide

if [[ "$public_nat" == --with-public-nat ]]; then
  if resource_missing compute routers list --regions="$region" \
    --filter="name=$router" --format='value(name)'; then
    "${gcp[@]}" compute routers create "$router" --network="$network" --region="$region"
  fi
  nat_names=$("${gcp[@]}" compute routers nats list --router="$router" --region="$region" --format='value(name)')
  if ! grep -Fxq "$nat_gateway" <<< "$nat_names"; then
    "${gcp[@]}" compute routers nats create "$nat_gateway" --router="$router" --region="$region" \
      --nat-custom-subnet-ip-ranges="$subnet:ALL" --auto-allocate-nat-external-ips
  fi
fi

if resource_missing sql instances list --filter="name=$instance" --format='value(name)'; then
  "${gcp[@]}" sql instances create "$instance" --zone="$zone" --edition=ENTERPRISE \
    --database-version=POSTGRES_18 --cpu=1 --memory=3840MiB --storage-type=SSD --storage-size=20 \
    --no-storage-auto-increase --availability-type=ZONAL --no-backup \
    --network="projects/$project_id/global/networks/$network" --no-assign-ip --ssl-mode=ENCRYPTED_ONLY
fi
if resource_missing sql databases list --instance="$instance" --filter='name=geolife' --format='value(name)'; then
  "${gcp[@]}" sql databases create geolife --instance="$instance"
fi

"${gcp[@]}" sql instances describe "$instance" \
  --format='table(name,state,databaseVersion,region,settings.tier)'

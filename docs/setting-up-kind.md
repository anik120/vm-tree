# Setting up a Kind cluster with KubeVirt

## Create Cluster 

```
$ kind create cluster
```

## Deploy kubeVirt 

```
$ export VERSION=$(curl -s https://storage.googleapis.com/kubevirt-prow/release/kubevirt/kubevirt/stable.txt)
$ echo $VERSION

$ kubectl create -f "https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-operator.yaml"
$ kubectl create -f "https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-cr.yaml"
```

## Verify Components 

```
$ kubectl get kubevirt.kubevirt.io/kubevirt -n kubevirt -o=jsonpath="{.status.phase}"
$ kubectl get all -n kubevirt
```


## Install CDI 

```
export VERSION=$(basename $(curl -s -w %{redirect_url} https://github.com/kubevirt/containerized-data-importer/releases/latest))
kubectl create -f https://github.com/kubevirt/containerized-data-importer/releases/download/$VERSION/cdi-operator.yaml
kubectl create -f https://github.com/kubevirt/containerized-data-importer/releases/download/$VERSION/cdi-cr.yaml
```

## Create a Second storage class (if you want to demo storage class migration) 

```
$ kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: standard-fast
  labels:
    storage-tier: fast
provisioner: rancher.io/local-path
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
EOF
storageclass.storage.k8s.io/standard-fast created

$ kubectl get sc      
NAME                 PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
standard (default)   rancher.io/local-path   Delete          WaitForFirstConsumer   false                  5d1h
standard-fast        rancher.io/local-path   Delete          Immediate              true                   79s
```

ref: https://kubevirt.io/quickstart_kind/
# Kubernetes Deployment

Deploy vcpkg-harbor on Kubernetes for scalable, production-ready deployments.

## Basic Deployment

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vcpkg-harbor
  labels:
    app: vcpkg-harbor
spec:
  replicas: 2
  selector:
    matchLabels:
      app: vcpkg-harbor
  template:
    metadata:
      labels:
        app: vcpkg-harbor
    spec:
      containers:
        - name: vcpkg-harbor
          image: ghcr.io/rennerdo30/vcpkg-harbor:latest
          ports:
            - containerPort: 15151
          env:
            - name: VCPKG_STORAGE_TYPE
              value: "s3"
            - name: VCPKG_S3_BUCKET
              value: "vcpkg-harbor"
            - name: VCPKG_S3_REGION
              value: "us-west-2"
          livenessProbe:
            httpGet:
              path: /health/live
              port: 15151
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 15151
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: vcpkg-harbor
spec:
  selector:
    app: vcpkg-harbor
  ports:
    - port: 80
      targetPort: 15151
  type: ClusterIP
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: vcpkg-harbor
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - vcpkg-cache.example.com
      secretName: vcpkg-harbor-tls
  rules:
    - host: vcpkg-cache.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: vcpkg-harbor
                port:
                  number: 80
```

## Configuration with Secrets

### Secret for Authentication

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: vcpkg-harbor-secrets
type: Opaque
stringData:
  auth-token: "your-secret-token"
```

### ConfigMap for Settings

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: vcpkg-harbor-config
data:
  VCPKG_STORAGE_TYPE: "s3"
  VCPKG_S3_BUCKET: "vcpkg-harbor"
  VCPKG_S3_REGION: "us-west-2"
  VCPKG_AUTH_ENABLED: "true"
  VCPKG_AUTH_TYPE: "token"
  VCPKG_LOG_JSON: "true"
```

### Using ConfigMap and Secret

```yaml
spec:
  containers:
    - name: vcpkg-harbor
      envFrom:
        - configMapRef:
            name: vcpkg-harbor-config
      env:
        - name: VCPKG_AUTH_TOKEN
          valueFrom:
            secretKeyRef:
              name: vcpkg-harbor-secrets
              key: auth-token
```

## AWS EKS with IRSA

Use IAM Roles for Service Accounts:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vcpkg-harbor
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789:role/vcpkg-harbor-s3
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      serviceAccountName: vcpkg-harbor
      containers:
        - name: vcpkg-harbor
          env:
            - name: VCPKG_STORAGE_TYPE
              value: "s3"
            # No credentials needed - uses IRSA
```

## GKE with Workload Identity

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vcpkg-harbor
  annotations:
    iam.gke.io/gcp-service-account: vcpkg-harbor@project.iam.gserviceaccount.com
```

## Monitoring

### ServiceMonitor for Prometheus Operator

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: vcpkg-harbor
spec:
  selector:
    matchLabels:
      app: vcpkg-harbor
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

## Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: vcpkg-harbor
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: vcpkg-harbor
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

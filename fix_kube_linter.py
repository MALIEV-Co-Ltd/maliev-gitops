#!/usr/bin/env python3
"""
Script to fix kube-linter issues in Kubernetes manifests
Fixes:
1. Add security contexts
2. Add resource requests/limits  
3. Fix probe configurations
4. Add image tags
"""

import os
import re
from pathlib import Path

def fix_deployment(file_path):
    """Fix a deployment YAML file"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # 1. Add security context if missing
    if 'securityContext:' not in content:
        # Find the containers section
        container_pattern = r'(      containers:\n        - name: .+\n          image: .+)'
        security_context = '''          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            runAsGroup: 3000
            readOnlyRootFilesystem: false
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL'''
        
        content = re.sub(
            container_pattern,
            r'\1\n' + security_context,
            content
        )
    
    # 2. Add resources if missing in base file
    if 'resources:' not in content and '/base/deployment.yaml' in file_path.replace('\\', '/'):
        # Find after imagePullPolicy
        resource_pattern = r'(          imagePullPolicy: Always\n)'
        resources = '''          resources:
            requests:
              cpu: "10m"
              memory: "96Mi"
            limits:
              cpu: "25m"
              memory: "128Mi"
'''
        content = re.sub(resource_pattern, r'\1' + resources, content)
    
    # 3. Add probe configurations if incomplete
    # Add initialDelaySeconds, timeoutSeconds, etc.
    if 'livenessProbe:' in content and 'initialDelaySeconds:' not in content:
        liveness_pattern = r'(          livenessProbe:\n            httpGet:\n              path: .+\n              port: \d+)'
        liveness_config = '''\n            initialDelaySeconds: 15
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3'''
        content = re.sub(liveness_pattern, r'\1' + liveness_config, content)
    
    if 'readinessProbe:' in content:
        # Check if readiness probe already has configuration
        if not re.search(r'readinessProbe:.*?initialDelaySeconds:', content, re.DOTALL):
            readiness_pattern = r'(          readinessProbe:\n            httpGet:\n              path: .+\n              port: \d+)\n'
            readiness_config = '''\n            initialDelaySeconds: 10
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
            successThreshold: 1
'''
            content = re.sub(readiness_pattern, r'\1' + readiness_config, content)
    
    # 4. Add image tag if missing
    image_pattern = r'(          image: asia-southeast1-docker\.pkg\.dev/maliev-website/maliev-website-artifact/maliev-[a-z\-]+)$'
    if re.search(image_pattern, content, re.MULTILINE):
        content = re.sub(
            image_pattern,
            r'\1:latest',
            content,
            flags=re.MULTILINE
        )
    
    # Write back if changed
    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    """Main function to process all deployment files"""
    base_dir = Path('3-apps')
    fixed_count = 0
    
    # Process all base deployment files
    for deployment_file in base_dir.glob('*/base/deployment.yaml'):
        print(f"Processing: {deployment_file}")
        if fix_deployment(str(deployment_file)):
            fixed_count += 1
            print(f"  [FIXED]")
        else:
            print(f"  [NO CHANGES]")
    
    # Process cluster-infra files
    infra_files = [
        '1-cluster-infra/04-redis/base/redis-statefulset.yaml',
        '1-cluster-infra/06-rabbitmq/base/rabbitmq-cluster.yaml'
    ]
    
    for infra_file in infra_files:
        if os.path.exists(infra_file):
            print(f"Processing: {infra_file}")
            if fix_deployment(infra_file):
                fixed_count += 1
                print(f"  [FIXED]")
            else:
                print(f"  [NO CHANGES]")
    
    print(f"\nTotal files fixed: {fixed_count}")

if __name__ == '__main__':
    main()

# PaymentService GitOps promotion

PaymentService remains disabled in every Argo CD environment until its deployment-readiness gates pass. The manifests under `argocd/environments/_disabled_apps` must not be moved by an image-promotion change.

PaymentService images are built once and promoted by the same immutable digest through these dedicated repositories:

- development: `asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-dev/maliev-payment-service`
- staging: `asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-staging/maliev-payment-service`
- production: `asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-prod/maliev-payment-service`

After the service workflow has published or copied the digest into the target repository, update the disabled overlay with:

```bash
./scripts/update-paymentservice-image.sh \
  <development|staging|production> \
  <environment-image-repository> \
  sha256:<64-lowercase-hex-characters>
```

The updater rejects tags, unexpected repositories, and malformed digests. It updates both the Kustomize image digest and `BuildMetadata__ImageDigest`, then renders the overlay before keeping the change. Promotion must stop if the target repository does not already contain the requested digest.

Run `./scripts/test-paymentservice-image-promotion.sh` to validate the updater, rendered image, and build-metadata parity without changing the checked-in overlays.

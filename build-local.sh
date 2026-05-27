#!/bin/bash
# ⚡ Bifrost — Local ARM64 build for OrbStack K8s (Mac mini M4 Pro)
# Skips GitHub Actions, builds native ARM64, loads directly to OrbStack

set -e

IMAGE_NAME="bifrost:local-arm64"
BUILD_CONTEXT="/Users/mimir/Developer"

echo "🔨 Building $IMAGE_NAME for OrbStack K8s..."
echo "   Build context: $BUILD_CONTEXT"

# Build using host's native ARM64
docker build \
  -t "$IMAGE_NAME" \
  -f "$BUILD_CONTEXT/Bifrost/Dockerfile" \
  "$BUILD_CONTEXT"

echo "✅ Build complete: $IMAGE_NAME"
echo ""
echo "📦 To deploy to OrbStack K8s:"
echo "   1. Update K8s deployment: image: bifrost:local-arm64"
echo "   2. Set imagePullPolicy: Never"
echo "   3. kubectl apply -f deployment.yaml"
echo ""
echo "💡 Or tag for ghcr:"
echo "   docker tag $IMAGE_NAME ghcr.io/megawiz-dev-team/bifrost:latest"
echo "   docker push ghcr.io/megawiz-dev-team/bifrost:latest"

#!/bin/bash
set -e  # エラーで即座に終了

echo "========================================="
echo "Building Memo AI for Vercel"
echo "========================================="

# 1. Clean previous build
echo "→ Cleaning previous build..."
rm -rf .vercel/output/static
rm -rf .vercel/output/config.json

# 2. Create output directory
echo "→ Creating output directory..."
mkdir -p .vercel/output/static

# 3. Copy static files
echo "→ Copying static files from public/ to .vercel/output/static/..."
cp -rv public/* .vercel/output/static/

# 4. Create Build Output API v3 config
echo "→ Creating Build Output API v3 config.json..."
cat > .vercel/output/config.json << 'EOF'
{
  "version": 3,
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "/api/index.py"
    }
  ]
}
EOF

# 5. Verify
echo "→ Verifying static files..."
ls -lah .vercel/output/static/
echo "→ Verifying config.json..."
cat .vercel/output/config.json

echo "========================================="
echo "✅ Build completed successfully!"
echo "========================================="

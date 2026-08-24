import './src/env';

import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Lean self-contained server bundle for the production Docker image
  // (apps/app/Dockerfile) -- see docs/architecture.md deployment notes.
  output: 'standalone',
};

export default nextConfig;

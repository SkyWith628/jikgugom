import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 배포용: 최소 의존성만 담은 standalone 서버 출력(.next/standalone)
  output: "standalone",
};

export default nextConfig;

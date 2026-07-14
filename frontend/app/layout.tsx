import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "砚台 · 财务学习工作台",
  description: "严格基于个人资料的 CPA 与税务师 AI 学习工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

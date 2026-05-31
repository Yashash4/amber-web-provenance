import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Amber · The Tamper Proof",
  description:
    "The forensic instrument that catches a store charging two countries different conditions for the same product in the same second, and prints a tamper-proof, independently re-verifiable evidence packet.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-mono antialiased">{children}</body>
    </html>
  );
}

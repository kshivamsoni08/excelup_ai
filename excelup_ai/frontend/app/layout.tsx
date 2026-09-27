import type { Metadata, Viewport } from "next";
import "./globals.css";
import Providers from "./providers";
import PwaRegister from "@/components/PwaRegister";

export const metadata: Metadata = {
  title: "ExcelUp AI - Skilling outcomes, measured honestly.",
  description:
    "Longitudinal skilling-outcomes and impact-measurement platform: consent-based outcome registry, one-tap follow-ups, employer validation, outcome-adjusted quality analytics.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: "#1E3A8A",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Providers>
          {children}
          <PwaRegister />
        </Providers>
      </body>
    </html>
  );
}

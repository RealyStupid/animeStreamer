import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PiraTube",
  description: "One stop for free pirated media!",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

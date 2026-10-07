import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AnimeWatcher",
  description: "One stop shop for free media!",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

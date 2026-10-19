import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bengaluru jobs | Jobmatch",
  description: "A focused browser for Bengaluru technology and AI roles.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

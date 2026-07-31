import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "HYC Inspection" };

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="ko"><body>{children}</body></html>;
}

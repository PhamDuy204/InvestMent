import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "InvestMent · V21 Cohort-Calibrated Risk Paper Monitor",
  description: "Public read-only realtime monitoring for the InvestMent V21 cohort-calibrated risk paper research engine.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

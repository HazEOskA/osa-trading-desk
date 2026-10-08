import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'OSA Trading Desk | Paper Only',
  description: 'Terminal symulacyjny Solana OSA — bez rzeczywistych zleceń',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pl"><body>{children}</body></html>;
}

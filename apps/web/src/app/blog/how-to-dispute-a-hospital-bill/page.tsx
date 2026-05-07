import { permanentRedirect } from 'next/navigation';

export default function Page(): never {
  permanentRedirect('/learn/how-to-dispute-a-hospital-bill');
}

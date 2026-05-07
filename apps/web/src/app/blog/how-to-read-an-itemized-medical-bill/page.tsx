import { permanentRedirect } from 'next/navigation';

export default function Page(): never {
  permanentRedirect('/learn/how-to-read-an-itemized-medical-bill');
}

import { permanentRedirect } from 'next/navigation';

export default function Page(): never {
  permanentRedirect('/learn/medical-billing-advocates');
}

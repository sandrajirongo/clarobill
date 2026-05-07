import { permanentRedirect } from 'next/navigation';

export default function BlogIndexPage(): never {
  permanentRedirect('/learn');
}

'use client';

import { useEffect, useRef } from 'react';

interface RevealProps {
  children: React.ReactNode;
  className?: string;
  as?: keyof JSX.IntrinsicElements;
}

// Wraps any content with an IntersectionObserver scroll-reveal effect.
// Sets data-reveal="visible" when the element enters the viewport,
// which triggers the CSS transition defined in globals.css.
export function Reveal({ children, className, as: Tag = 'div' }: RevealProps): JSX.Element {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          el.setAttribute('data-reveal', 'visible');
          observer.unobserve(el);
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    // @ts-expect-error — dynamic tag typing
    <Tag ref={ref} data-reveal="" className={className}>
      {children}
    </Tag>
  );
}

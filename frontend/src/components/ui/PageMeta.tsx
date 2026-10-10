import { useEffect } from 'react';

export function PageMeta({ title, description }: { title: string; description: string }) {
  useEffect(() => {
    document.title = `${title} — Clyptusap.ai`;
    const meta = document.querySelector('meta[name="description"]');
    meta?.setAttribute('content', description);
  }, [description, title]);
  return null;
}

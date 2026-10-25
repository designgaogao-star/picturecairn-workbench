import type { JSX } from 'preact';
import { useLayoutEffect, useRef } from 'preact/hooks';

/** Release the decoded resource when a layer leaves the UI, including completed images. */
export function ImageElement(props: Omit<JSX.IntrinsicElements['img'], 'ref'>) {
  const ref = useRef<HTMLImageElement>(null);
  useLayoutEffect(() => {
    const image = ref.current;
    return () => {
      image?.removeAttribute('src'); image?.removeAttribute('srcset');
      (window as unknown as { galleryImageResources?: { release: () => void } }).galleryImageResources?.release();
    };
  }, []);
  return <img {...props} ref={ref} />;
}
